# Canto rsync Plugin
# by Jack Miller
# v1.1

# This implements a lightweight remote sync based around rsync to a remote
# server, or copying to mounted filesystem, etc.

ENABLED = False
#ENABLED = True

# SSH
# For ssh based rsync (remote hosts) you should have key authentication setup
# so it runs without prompting for a password.

#SYNC_LOCATION = "user@host:"

# Dropbox, assuming you have dropbox running
#SYNC_LOCATION = "~/Dropbox/"

# Mount / NFS / sshfs etc.
#SYNC_LOCATION = "/mnt/wherever/"

# Synchronization interval in seconds
INTERVAL = 5 * 60

# How long, in seconds, we should wait for the initial sync. Setting to 0 will
# cause a sync to occur before any other items can be read from disk, which
# ensures you won't see any old items, but also means a full sync has to occur
# before any items make it to the client and causes a long delay on startup.

INITIAL_SYNC = 30

#============================================
# Probably won't need to change these.

# rsync
#  -a (archive mode) to preserve times / perms
#  -v (verbose) to output interesting log info
#  -z (compress) to save bandwidth

CMD = [ "rsync", "-avz"]

targets = { "db" : ".cantofeeds",
            "conf" : ".cantoconf"
}

from canto_next.plugins import check_program

check_program("canto-daemon", "canto-remote")

if not ENABLED:
    raise Exception("Plugin disabled.")

from canto_next.hooks import on_hook, call_hook
from canto_next.canto_backend import DaemonBackendPlugin
from canto_next.remote import DaemonRemotePlugin

from canto_next.config import parse_locks, parse_unlocks, config
from canto_next.locks import config_lock, feed_lock
from canto_next.feed import wlock_all, wunlock_all, rlock_all, runlock_all, allfeeds
from canto_next.tag import alltags

from tempfile import mkstemp
import subprocess
import logging
import shutil
import gzip
import json
import time
import os

log = logging.getLogger("SYNC-RSYNC")

class CantoFileSync(DaemonBackendPlugin):
    def __init__(self, backend):
        self.plugin_attrs = {
                "cmd_sync" : self.cmd_sync,
                "cmd_syncto" : self.cmd_syncto
        }

        self.backend = backend

        # Plugin __init__ happens extremely early so that plugin types can be
        # used in validating configuration, etc. We use the daemon_serving hook
        # to do our work after the config and storage is setup.

        on_hook("daemon_serving", self.setup)

    def setup(self):

        # Use setattributes and setconfigs commands to determine that we are the fresh
        # copy that should be synchronized.

        on_hook("daemon_end_loop", self.loop)
        on_hook("daemon_pre_setconfigs", self.pre_setconfigs)
        on_hook("daemon_pre_setattributes", self.pre_setattributes)
        on_hook("daemon_exit", self.cmd_syncto)

        self.reset()

        # sync will grab files, check the timediff on the file if the file is
        # actually newer (like we failed to sync last time) then it will set
        # fresh_config and do a syncto.

        self.sync_ts = 0
        if (INITIAL_SYNC == 0):
            self.cmd_sync()
        elif (INITIAL_SYNC < INTERVAL):
            self.sync_ts = time.time() - (INTERVAL - INITIAL_SYNC)

    def reset(self):
        self.fresh_config = False
        self.sent_config = False

        self.fresh_content = False
        self.sent_content = False

    # Use hooks to determine when we need to copy stuff.

    def pre_setattributes(self, socket, args):
        self.fresh_content = True

    def pre_setconfigs(self, socket, args):
        self.fresh_config = True

    # Open a shelf at path, determine if it's been changed more recently than
    # our current shelf.

    def time_diff(self, path):
        log.debug("Checking if %s is older than our shelf.", path)

        try:
            fp = gzip.open(path, "rt", 9, "UTF-8")
            s = json.load(fp)
            fp.close()
        except:
            # If something messed up, assume that the sync failed and
            # pretend that we're newer anyway.
            return -1

        if "control" in s and "canto-user-modified" in s["control"]:
            remote_stamp = s["control"]["canto-user-modified"]
        else:
            log.debug("Remote has no timestamp")
            return -1

        rlock_all()
        if "control" in self.backend.shelf and "canto-user-modified" in self.backend.shelf["control"]:
            local_stamp = self.backend.shelf["control"]["canto-user-modified"]
            runlock_all()
        else:
            log.debug("We have no timestamp")
            runlock_all()
            return 1

        if remote_stamp > local_stamp:
            log.debug("db: We are older")
        elif remote_stamp == local_stamp:
            log.debug("db: We are equal")
        else:
            log.debug("db: We are newer")

        return remote_stamp - local_stamp

    def cmd_syncto(self, socket = None, args = None):
        if self.fresh_content:
            f, fname = mkstemp()
            os.close(f)

            # Lock feeds to make sure nothing's in flight
            wlock_all()

            # Sync the shelf so it's all on disk

            self.backend.shelf.sync()

            shutil.copyfile(self.backend.feed_path, fname)

            # Let everything else continue
            wunlock_all()

            call_hook("daemon_syncto", [ "db", fname ])

            # Cleanup temp file
            os.unlink(fname)

            self.fresh_content = False
            self.sent_content = True

        if self.fresh_config:
            f, fname = mkstemp()
            os.close(f)

            config_lock.acquire_read()
            shutil.copyfile(self.backend.conf_path, fname)
            config_lock.release_read()

            call_hook("daemon_syncto", [ "conf", fname ])

            os.unlink(fname)

            self.fresh_config = False
            self.sent_config = True

    def cmd_sync(self, socket = None, args = None):
        needs_syncto = False

        if not self.sent_config:
            f, fname = mkstemp()
            os.close(f)

            call_hook("daemon_syncfrom", [ "conf", fname ])

            conf_stat = os.stat(self.backend.conf_path)
            sync_stat = os.stat(fname)

            log.debug('conf: %s sync: %s' % (conf_stat.st_mtime, sync_stat.st_mtime))

            diff = sync_stat.st_mtime - conf_stat.st_mtime

            # Will be empty tempfile if syncfrom failed.

            if sync_stat.st_size != 0:
                if diff > 0:
                    log.debug("conf: We are older")
                    parse_locks()
                    shutil.move(fname, self.backend.conf_path)
                    config.parse()
                    parse_unlocks()

                    # Echo these changes to all connected sockets that care
                    for socket in self.backend.watches["config"]:
                        self.backend.in_configs({}, socket)

                elif diff == 0:
                    log.debug("conf: We are equal")
                    os.unlink(fname)
                else:
                    log.debug("conf: We are newer")
                    os.unlink(fname)
                    self.fresh_config = True
                    needs_syncto = True
            else:
                os.unlink(fname)

        if not self.sent_content:
            f, fname = mkstemp()
            os.close(f)

            call_hook("daemon_syncfrom", [ "db", fname ])

            diff = self.time_diff(fname)

            if diff > 0:
                # Lock feeds to make sure nothing's in flight
                wlock_all()

                # Close the file so we can replace it.
                self.backend.shelf.close()

                shutil.move(fname, self.backend.feed_path)

                self.backend.shelf.open()

                # Clear out all of the currently tagged items. Usually on
                # update, we're able to discard items that we have in old
                # content, but aren't in new. But since we just replaced all of
                # our old content with a totally fresh copy, we might not know
                # they exist. Can't use reset() because we don't want to lose
                # configuration.

                alltags.clear_tags()

                # First half of wunlock_all, release these locks so
                # fetch threads can get locks

                for feed in sorted(allfeeds.feeds.keys()):
                    allfeeds.feeds[feed].lock.release_write()

                # Complete wunlock_all()
                feed_lock.release_write()

                # Force feeds to be repopulated from disk, which will handle
                # communicating changes to connections

                self.backend.fetch.fetch(True, True)
                self.backend.fetch.reap(True)

            # Equal, just clear it up

            elif diff == 0:
                os.unlink(fname)

            # If we're actually newer on a syncfrom then make syncto happen
            # next time. This can happen on init.

            else:
                os.unlink(fname)
                self.fresh_content = True
                needs_syncto = True

        if needs_syncto:
            self.cmd_syncto()

        self.reset()

    def loop(self):
        ts = time.time()
        if (ts - self.sync_ts >= INTERVAL):
            self.cmd_sync()
            self.sync_ts = ts

class RemoteSync(DaemonRemotePlugin):
    def __init__(self, remote):
        self.plugin_attrs = { "cmd_sync" : self.cmd_sync }
        self.remote = remote

        on_hook("remote_print_commands", self.print_sync_commands)

    def print_sync_commands(self):
        print("\nSync Plugin")
        print("\tsync - sync the daemon")

    def cmd_sync(self):
        """USAGE: canto-remote sync
    Synchronize this daemon with a remote daemon"""
        self.remote.write("SYNC", {})

# Each of these gets called with a "target" (i.e. a type of file we want to
# sync) and a temporary filename to either copy to somewhere else or overwrite.

# NOTE: The logic for whether this file actually gets used is in sync.py. For
# the feeds database, it takes the last user modification into account because
# any db with a running daemon is going to be modified often by new feed info,
# making mtime worthless. For the config, however, it's only written when a
# change has been made, so mtime should be sufficient. This is why we use -a to
# rsync.

def rsync_to(target, fname):

    if target in targets:
        cmd = CMD + [ fname, SYNC_LOCATION + targets[target] ]
    else:
        log.warn("Unknown file to sync: %s" % target)
        return

    log.debug("Syncto cmd: %s", cmd)
    
    try:
        out = subprocess.check_output(cmd)
    except Exception as e:
        log.warn("Command %s : %s" % (cmd, e))
    else:
        log.debug("Syncto output: %s", out)

def rsync_from(target, fname):
    if target in targets:
        cmd = CMD + [ SYNC_LOCATION + targets[target], fname ]
    else:
        log.warn("Unknown file to sync: %s" % target)
        return

    log.debug("Syncfrom cmd: %s", cmd)

    try:
        out = subprocess.check_output(cmd)
    except Exception as e:
        log.warn("Command %s : %s" % (cmd, e))
    else:
        log.debug("Syncfrom output: %s", out)

on_hook("daemon_syncfrom", rsync_from)
on_hook("daemon_syncto", rsync_to)
