# Canto Sync Plugin
# by Jack Miller
# v1.0

# This implements a basic foundation for file based sync plugins.
#
# The idea is that we can put all of the logic for locking, repopulating, and
# adding commands to the remote here, and then use light plugins to actually
# perform the moves from wherever.

# Interval to perform syncs

INTERVAL = 5 * 60

from canto_next.hooks import on_hook, call_hook
from canto_next.canto_backend import DaemonBackendPlugin
from canto_next.remote import DaemonRemotePlugin

from canto_next.config import parse_locks, parse_unlocks
from canto_next.locks import config_lock, feed_lock
from canto_next.feed import wlock_all, wunlock_all, rlock_all, runlock_all, allfeeds

from tempfile import mkstemp
import logging
import shelve
import shutil
import os

log = logging.getLogger("SYNC")

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

        self.sync_interval = INTERVAL

        on_hook("daemon_end_loop", self.loop)
        on_hook("daemon_pre_setconfigs", self.pre_setconfigs)
        on_hook("daemon_pre_setattributes", self.pre_setattributes)
        on_hook("daemon_exit", self.cmd_syncto)

        self.reset()

        # Do the initial sync

        # sync will grab files, check the timediff on the file if the file is
        # actually newer (like we failed to sync last time) then it will set
        # fresh_config and do a syncto.

        self.cmd_sync()

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
        log.debug("Checking if %s is older than our shelf." % path)

        try:
            s = shelve.open(path, 'r')
        except:
            # If something messed up, assume that the sync failed and
            # pretend that we're newer anyway.
            return -1

        if "control" in s and "canto-user-modified" in s["control"]:
            remote_stamp = s["control"]["canto-user-modified"]
            s.close()
        else:
            s.close()
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
                    self.backend.conf.parse()
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

                # First half of wunlock_all, release these locks so
                # fetch threads can get locks

                for feed in sorted(allfeeds.feeds.keys()):
                    allfeeds.feeds[feed].lock.release_write()

                # Force feeds to be repopulated from disk, which will handle
                # communicating changes to connections

                self.backend.fetch.fetch(True, True)
                self.backend.fetch.reap(True)

                # Complete wunlock_all()
                feed_lock.release_write()

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
        self.sync_interval -= 1
        if self.sync_interval <= 0:
            self.cmd_sync()

            self.sync_interval = INTERVAL

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
