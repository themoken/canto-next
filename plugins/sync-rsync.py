# Canto rsync Plugin
# by Jack Miller
# v1.0

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

from canto_next.hooks import on_hook

import subprocess
import logging

log = logging.getLogger("SYNC-RSYNC")

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

    log.debug("Syncto cmd: %s" % (cmd,))

    try:
        out = subprocess.check_output(cmd)
    except Exception as e:
        log.warn("Command %s : %s" % (cmd, e))
    else:
        log.debug("Syncto output: %s" % out)

def rsync_from(target, fname):
    if target in targets:
        cmd = CMD + [ SYNC_LOCATION + targets[target], fname ]
    else:
        log.warn("Unknown file to sync: %s" % target)
        return

    log.debug("Syncfrom cmd: %s" % (cmd,))

    try:
        out = subprocess.check_output(cmd)
    except Exception as e:
        log.warn("Command %s : %s" % (cmd, e))
    else:
        log.debug("Syncfrom output: %s" % out)

if ENABLED:
    on_hook("daemon_syncfrom", rsync_from)
    on_hook("daemon_syncto", rsync_to)
