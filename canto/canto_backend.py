# -*- coding: utf-8 -*-
#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# This Backend class is the core of the daemon's specific protocol.

from server import CantoServer
from config import CantoConfig
from storage import CantoShelf
from encoding import encoder, decoder

import traceback
import logging
import signal
import getopt
import Queue
import fcntl
import time
import sys
import os

# By default this will log to stderr.
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
        # Signal handlers
        self.alarmed = 0
        signal.signal(signal.SIGALRM, self.sig_alrm)
        signal.alarm(1)

        # Log verbosity
        # 0 = normal operation
        # 1 = log all debug messages
        # 2 = log all debug messages AND signals
        self.verbosity = 1

        # No bad arguments.
        if self.args():
            sys.exit(-1)

        # No invalid paths.
        if self.ensure_paths():
            sys.exit(-1)

        # These paths are now guaranteed to valid.
        # Keep in mind though the above *doesn't* test whether feeds
        # or conf are *valid*, just that we have permissions on them.

        self.feed_path = self.conf_dir + "/feeds"
        self.pid_path = self.conf_dir + "/pid"
        self.log_path = self.conf_dir + "/daemon-log"
        self.conf_path = self.conf_dir + "/conf"

        # Get pid lock.
        if self.pid_lock():
            sys.exit(-1)

        # Previous to this line, all output is just error messages to stderr.
        self.set_log()

        # Initial log chatter.
        log.info("Canto Daemon started.")
        if self.verbosity:
            log.debug("verbosity = %d" % self.verbosity)
        log.debug("conf_dir = %s" % self.conf_dir)

        # Actual start.
        self.get_storage()
        self.get_config()

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

            if self.alarmed:
                if self.verbosity > 1:
                    log.debug("Alarmed.")
                self.alarmed = False

            time.sleep(100)

    # This function parses and validates all of the command line arguments.
    def args(self, args=None):
        if not args:
            args = sys.argv[1:]

        try:
            optlist = getopt.getopt(args, 'D:v', ["dir="])[0]
        except getopt.GetoptError, e:
            log.error("Error: %s" % e.msg)
            return -1

        self.conf_dir = os.path.expanduser(u"~/.canto-ng/")

        for opt, arg in optlist:
            # -D base configuration directory. Highest priority.
            if opt in ["-D", "--dir"]:
                self.conf_dir = os.path.expanduser(decoder(arg))
                self.conf_dir = os.path.realpath(self.conf_dir)

            # -v increase verbosity
            elif opt in ["-v"]:
                self.verbosity += 1

        return 0

    def sig_alrm(self, a, b):
        self.alarmed = 1
        signal.alarm(1)

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
        for f in [ "feeds", "conf", "daemon-log", "pid"]:
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

    def pid_lock(self):
        self.pidfile = open(self.pid_path, "a")
        try:
            fcntl.flock(self.pidfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.pidfile.seek(0)
            self.pidfile.write("%d" % os.getpid())
            self.pidfile.flush()
        except:
            log.error("Error: Another canto-daemon is running here.")
            return -1
        return None

    def pid_unlock(self):
        fcntl.flock(self.pidfile.fileno(), fcntl.LOCK_UN)
        self.pidfile.close()

    # Reset basic log info to log to the right file.
    def set_log(self):
        f = open(self.log_path, "w")
        os.dup2(f.fileno(), sys.stderr.fileno())

    # Bring up storage, the only errors possible at this point are 
    # fatal and handled lower in CantoShelf.

    def get_storage(self):
        self.shelf = CantoShelf(self.feed_path)

    # Bring up config, the only errors possible at this point will
    # be fatal and handled lower in CantoConfig.

    def get_config(self):
        self.conf = CantoConfig(self.conf_path, self.shelf)
        self.conf.parse()

    def start(self):
        try:
            self.init()
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
        self.pid_unlock()
        sys.exit(0)
