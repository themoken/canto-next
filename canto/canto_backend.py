# -*- coding: utf-8 -*-
#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# This Backend class is the core of the daemon's specific protocol.

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

log = logging.getLogger("CANTO-DAEMON")

class CantoBackend(CantoServer):

    # We don't do init on instantiation for testing purposes.
    def __init__(self):
        pass

    def init(self):
        # Bad arguments.
        if self.args():
            sys.exit(-1)

        # Invalid paths.
        if self.ensure_paths():
            sys.exit(-1)

        CantoServer.__init__(self, self.conf_dir + "/.canto_socket",\
                Queue.Queue())

    # Simple PING response, PONG.
    def pong(self, socket, args):
        self.write(socket, "PONG", "")

    # The workhorse that maps all requests to their handlers.
    def run(self):
        while 1:
            if not self.queue.empty():
                (socket, (cmd, args)) = self.queue.get()
                if cmd == "PING":
                    self.pong(socket, args)
            self.check_conns()

    # This function parses and validates all of the command line arguments.
    def args(self, args=None):
        if not args:
            args = sys.argv[1:]

        try:
            optlist = getopt.getopt(args, 'D:', ["dir="])[0]
        except getopt.GetoptError, e:
            log.error("Error: %s" % e.msg)
            return -1

        self.conf_dir = os.path.expanduser(u"~/.canto-ng/")

        for opt, arg in optlist:
            # -D base configuration directory. Highest priority.
            if opt in ["-D", "--dir"]:
                self.conf_dir = os.path.expanduser(decoder(arg))
                self.conf_dir = os.path.realpath(self.conf_dir)

        log.debug("conf_dir = %s" % self.conf_dir)
        
        return 0

    # This function makes sure that the configuration paths are all R/W or
    # creatable.

    def ensure_paths(self):
        if os.path.exists(self.conf_dir):
            if not os.path.isdir(self.conf_dir):
                log.error("Error: %s is not a directory." % self.conf_dir)
                return -1
            if not os.access(self.conf_dir, os.R_OK):
                log.error("Error: %s is not readable." % self.conf_dir)
                return -1
            if not os.access(self.conf_dir, os.W_OK):
                log.error("Error: %s is not writable." % self.conf_dir)
                return -1
        else:
            try:
                os.makedirs(self.conf_dir)
            except e:
                log.error("Exception making %s : %s" % (self.conf_dir, e.msg))
                return -1
        return self.ensure_files()

    def ensure_files(self):
        for f in [ "feeds", "conf", "log" ]:
            p = self.conf_dir + "/" + f
            if os.path.exists(p):
                if not os.path.isfile(p):
                    log.error("Error: %s is not a file." % p)
                    return -1
                if not os.access(p, os.R_OK):
                    log.error("Error: %s is not readable." % p)
                    return -1
                if not os.access(p, os.W_OK):
                    log.error("Error: %s is not writable." % p)
                    return -1
        return None

    def start(self):
        self.init()
        try:
            self.run()

        # Cleanly shutdown on ^C.
        except KeyboardInterrupt:
            pass

        # Pretty print any non-Keyboard exceptions.
        except Exception, e:
            tb = traceback.format_exc(e)
            log.error("Exiting on exception:")
            log.error("\n" + "".join(tb))
            return -1
        self.exit()
        sys.exit(0)
