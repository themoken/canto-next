#!/usr/bin/python
# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from server import CantoServer
from encoding import encoder, decoder

import traceback
import logging
import getopt
import Queue
import sys
import os

logging.basicConfig(
        filemode = "w",
        format = "%(asctime)s : %(name)s -> %(message)s",
        datefmt = "%H:%M:%S",
        level = logging.DEBUG
)

log = logging.getLogger("CANTO-BACKEND")

SOCKET_NAME=".canto_socket"

class CantoBackend(CantoServer):

    # We don't do init on instantiation for testing purposes.
    def __init__(self):
        pass

    def init(self):
        # Bad arguments
        if self.args():
            sys.exit(-1)

        # Invalid paths
        if self.ensure_paths():
            sys.exit(-1)

        CantoServer.__init__(self, SOCKET_NAME, Queue.Queue())

    def pong(self, socket, args):
        self.write(socket, "PONG", "")

    def run(self):
        while 1:
            if not self.queue.empty():
                (socket, (cmd, args)) = self.queue.get()
                if cmd == "PING":
                    self.pong(socket, args)
            self.check_conns()

    def args(self, args=None):
        if not args:
            args = sys.argv[1:]

        try:
            optlist = getopt.getopt(args, 'D:i',\
                    ["dir=", "initonly"])[0]
        except getopt.GetoptError, e:
            log.error("Error: %s" % e.msg)
            return -1

        self.conf_dir = os.path.expanduser(u"~/.canto-ng/")

        for opt, arg in optlist:
            if opt in ["-D", "--dir"]:
                self.conf_dir = os.path.expanduser(decoder(arg))
                self.conf_dir = os.path.realpath(self.conf_dir)

        log.debug("conf_dir = %s" % self.conf_dir)

        return 0

    def ensure_paths(self):
        for p in [self.conf_dir]:
            if os.path.exists(p):
                if not os.path.isdir(p):
                    log.error("Error: %s is not a directory." % p)
                    return -1
                if not os.access(p, os.R_OK):
                    log.error("Error: %s is not readable." % p)
                    return -1
                if not os.access(p, os.W_OK):
                    log.error("Error: %s is not writable." % p)
                    return -1
            else:
                try:
                    os.makedirs(p)
                except e:
                    log.error("Exception making %s : %s" % (p, e.msg))
                    return -1
        return None

    def start(self):
        self.init()
        try:
            back.run()
        except KeyboardInterrupt:
            pass
        except:
            tb = traceback.format_stack()
            log.error("Exiting on exception:")
            log.error("\n" + "".join(tb))
            return -1
        back.exit()
        sys.exit(0)

if __name__ == "__main__":
    back = CantoBackend()
    back.start()
