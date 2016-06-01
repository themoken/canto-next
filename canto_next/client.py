# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .protocol import CantoSocket
from .hooks import call_hook

import logging
import fcntl
import errno
import time
import sys
import os

log = logging.getLogger("CLIENT")

class CantoClient(CantoSocket):
    def __init__(self, socket_name, **kwargs):
        kwargs["server"] = False
        CantoSocket.__init__(self, socket_name, **kwargs)

    def connect(self):
        conn = CantoSocket.connect(self)
        call_hook("client_new_socket", [conn])
        return conn


    # Test whether we can lock the pidfile, and if we can, fork the daemon
    # with the proper arguments.

    def start_daemon(self):
        pidfile = self.conf_dir + "/pid"
        if os.path.exists(pidfile) and os.path.isfile(pidfile):
            try:
                pf = open(pidfile, "a+")
                fcntl.flock(pf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                if os.path.exists(self.socket_path):
                    os.unlink(self.socket_path)
                fcntl.flock(pf.fileno(), fcntl.LOCK_UN)
                pf.close()
            except IOError as e:
                if e.errno == errno.EAGAIN:
                    # If we failed to get a lock, then the daemon is running
                    # and we're done.
                    return

        pid = os.fork()
        if not pid:
            # Shutup any log output before canto-daemon sets up it's log
            # (particularly the error that one is already running)

            fd = os.open("/dev/null", os.O_RDWR)
            os.dup2(fd, sys.stderr.fileno())

            cmd = "canto-daemon -D " + self.conf_dir
            if self.verbosity > 0:
                cmd += " -" + ("v" * self.verbosity)

            os.setpgid(os.getpid(), os.getpid())
            os.execve("/bin/sh", ["/bin/sh", "-c", cmd], os.environ)

            # Should never get here, but just in case.
            sys.exit(-1)

        while not os.path.exists(self.socket_path):
            time.sleep(0.1)

        return pid

    # Write a (cmd, args)
    def write(self, cmd, args, conn=0):
        return self.do_write(self.sockets[conn], cmd, args)

    # Read a (cmd, args)
    def read(self, timeout=None, conn=0):
        return self.do_read(self.sockets[conn], timeout)
