# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .protocol import CantoSocket
from .hooks import call_hook

import logging
import select
import getopt
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

    # Sets self.conf_dir and self.socket_path

    def common_args(self, extrashort = "", extralong = []):
        self.port = -1
        self.addr = None

        try:
            optlist, sys.argv =\
                    getopt.getopt(sys.argv[1:], 'D:p:a:' + extrashort,\
                    ["dir=", "port=", "address="] + extralong)
        except getopt.GetoptError as e:
            log.error("Error: %s" % e.msg)
            return -1

        self.conf_dir = os.path.expanduser("~/.canto-ng/")

        self.location_args = []

        for opt, arg in optlist:
            if opt in [ "-D", "--dir"]:
                self.conf_dir = os.path.expanduser(arg)
                self.conf_dir = os.path.realpath(self.conf_dir)
                self.location_args += [ opt, arg ]

            elif opt in [ "-p", "--port"]:
                try:
                    self.port = int(arg)
                    if self.port < 0:
                        raise Exception
                except:
                    log.error("Error: Port must be >0 integer.")
                    return -1
                self.location_args += [ opt, arg ]

            elif opt in [ "-a", "--address"]:
                self.addr = arg
                self.location_args += [ opt, arg ]

        self.socket_path = self.conf_dir + "/.canto_socket"

        return optlist

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

            os.setpgid(os.getpid(), os.getpid())
            os.execve("/bin/sh",
                     ["/bin/sh", "-c", "canto-daemon -D " + self.conf_dir],
                     os.environ)

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
