# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# This Backend class is the core of the daemon's specific protocol.

from fetch import CantoFetch
from server import CantoServer
from config import CantoConfig
from storage import CantoShelf
from encoding import encoder, decoder
from tag import alltags
from feed import allfeeds

import traceback
import logging
import signal
import getopt
import Queue
import fcntl
import errno
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

    def init(self, args=None):
        # Log verbosity
        # 0 = normal operation
        # 1 = log all debug messages
        # 2 = log all debug messages AND signals
        self.verbosity = 1

        # Shelf for feeds:
        self.fetch = None
        self.fetch_timer = 0

        self.shelf = None

        # No bad arguments.
        if self.args(args):
            sys.exit(-1)

        # No invalid paths.
        if self.ensure_paths():
            sys.exit(-1)

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
        self.get_fetch()

        CantoServer.__init__(self, self.conf_dir + "/.canto_socket",\
                Queue.Queue())

        # Signal handlers kickoff after everything else is init'd
        self.alarmed = 0
        signal.signal(signal.SIGALRM, self.sig_alrm)
        signal.alarm(1)

    def apply_filters(self, tag):
        log.debug("Applying filter: %s" % self.conf.global_filter.path)
        return self.conf.global_filter(tag)

    # Simple PING response, PONG.
    def pong(self, socket, args):
        self.write(socket, "PONG", u"")

    # LISTFEEDS -> (tag, URL) for all feeds
    def listfeeds(self, socket, args):
        feeds = []
        for feed in self.conf.feeds:
            feeds.append((feed.name, feed.URL))
        self.write(socket, "LISTFEEDS", feeds)

    # ITEMS tag|[tags] -> { tag : [ ids ], tag2 : ... }
    def items(self, socket, args):
        ids = []

        if type(args) == unicode:
            tags = [ args ]
        elif type(args) == list:
            tags = args
        else:
            log.error("Invalid type: %s" % type(args))
            return

        log.debug("TAGS: %s" % tags)
        response = {}
        for tag in tags:
            # get_tag returns a list invariably, but may be empty.
            response[tag] = self.apply_filters(alltags.get_tag(tag))

        self.write(socket, "ITEMS", response)

    # ATTRIBUTES { id : [ attribs .. ] .. } ->
    # { id : { attribute : value } ... }

    def attributes(self, socket, args):

        log.debug("ATTRIBUTES args: %s" % args)

        ret = {}
        for i in args.keys():
            # i[0] = URL, i[1] = feed id

            f = allfeeds[i[0]]
            try:
                ret[i] = f.get_attributes(i, args[i])
            except:
                # Item not found
                ret[i] = None

        self.write(socket, "ATTRIBUTES", ret)

    # SETATTRIBUTES { id : { attribute : value } ... } -> None

    def setattributes(self, socket, args):
        log.debug("SETATTRIBUTES %s" % args)

        ret = {}
        for i in args.keys():
            # i[0] = URL, i[1] = feed id
            f = allfeeds[i[0]]
            try:
                f.set_attributes(i, args[i])
            except:
                # Item not found.
                pass

    # The workhorse that maps all requests to their handlers.
    def run(self):
        while 1:
            if not self.queue.empty():
                (socket, (cmd, args)) = self.queue.get()

                if cmd == "PING":
                    self.pong(socket, args)
                elif cmd == "LISTFEEDS":
                    self.listfeeds(socket, args)
                elif cmd == "ITEMS":
                    self.items(socket, args)
                elif cmd == "ATTRIBUTES":
                    self.attributes(socket, args)
                elif cmd == "SETATTRIBUTES":
                    self.setattributes(socket, args)
                elif cmd == "DIE":
                    log.info("Received DIE.")
                    return
                else:
                    log.info("Got unknown command: %s" % (cmd))

            self.check_conns()

            # If the threads are ready, process them and
            # write them to disk.

            if self.fetch.threads_ready():
                self.fetch.process()

            if self.alarmed:
                # Decrement all timers
                self.fetch_timer -= 1

                if self.verbosity > 1:
                    log.debug("Alarmed.")

                # Check whether feeds need to be updated and fetch
                # them if necessary.

                if self.fetch_timer <= 0:
                    self.fetch.fetch()
                    self.fetch_timer = 60

                self.alarmed = False

            time.sleep(0.01)

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

        # These paths are now guaranteed to read/writable.

        self.feed_path = self.conf_dir + "/feeds"
        self.pid_path = self.conf_dir + "/pid"
        self.log_path = self.conf_dir + "/daemon-log"
        self.conf_path = self.conf_dir + "/conf"

        return None

    def pid_lock(self):
        self.pidfile = open(self.pid_path, "a+")
        try:
            fcntl.flock(self.pidfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.pidfile.seek(0, 0)
            self.pidfile.truncate()
            self.pidfile.write("%d" % os.getpid())
            self.pidfile.flush()
        except IOError, e:
            if e.errno == errno.EAGAIN:
                log.error("Error: Another canto-daemon is running here.")
                return -1
            raise
        return None

    def pid_unlock(self):
        log.debug("Unlocking pidfile.")
        fcntl.flock(self.pidfile.fileno(), fcntl.LOCK_UN)
        self.pidfile.close()
        log.debug("Unlocked.")

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

    def get_fetch(self):
        self.fetch = CantoFetch(self.shelf, self.conf.feeds)
        self.fetch.fetch()

    def start(self, args=None):
        try:
            self.init(args)
            self.run()
            log.info("Exiting cleanly.")

        # Cleanly shutdown on ^C.
        except KeyboardInterrupt:
            pass

        # Pretty print any non-Keyboard exceptions.
        except Exception, e:
            tb = traceback.format_exc(e)
            log.error("Exiting on exception:")
            log.error("\n" + "".join(tb))

        self.exit()
        self.pid_unlock()
        sys.exit(0)
