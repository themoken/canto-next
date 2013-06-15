# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# This Backend class is the core of the daemon's specific protocol.

# PROTOCOL_VERSION History:
# 0.1 - Initial versioned commit.
# 0.2 - Modified tags to escape the : separator such that tags handed out are
#       immediaely read to be used as [ Tag -whatever- ] config headers.

version = REPLACE_WITH_VERSION

CANTO_PROTOCOL_VERSION = 0.4

from .feed import allfeeds
from .encoding import encoder
from .protect import protection
from .server import CantoServer
from .config import CantoConfig
from .storage import CantoShelf
from .fetch import CantoFetch
from .hooks import on_hook, call_hook
from .tag import alltags
from .transform import eval_transform
from .plugins import try_plugins

import traceback
import logging
import signal
import getopt
import queue
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
        level = logging.INFO
)

log = logging.getLogger("CANTO-DAEMON")

FETCH_CHECK_INTERVAL = 60
TRIM_INTERVAL = 300

class CantoBackend(CantoServer):

    # We want to invoke CantoServer's __init__ manually, and
    # not on instantiation.

    def __init__(self):
        pass

    def init(self):
        # Log verbosity
        self.verbosity = 0

        # Shelf for feeds:
        self.fetch = None
        self.fetch_timer = 0

        # Timer to flush the database changes
        # and trim the file down to size.
        self.trim_timer = TRIM_INTERVAL

        # Whether fetching is inhibited.
        self.no_fetch = False

        # Whether we should use the shelf writeback.
        self.writeback = True

        self.watches = { "new_tags" : [],
                         "del_tags" : [],
                         "config" : [],
                         "tags" : {} }

        self.autoattr = {}

        # Per socket transforms.
        self.socket_transforms = {}

        self.shelf = None

        self.port = -1
        self.intf = ''

        # No bad arguments.
        if self.args():
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
            rootlog = logging.getLogger()
            rootlog.setLevel(max(rootlog.level - 10 * self.verbosity,0))
            log.info("verbosity = %d" % self.verbosity)

        log.info("conf_dir = %s" % self.conf_dir)

        # Evaluate any plugins
        try_plugins(self.conf_dir)

        if self.no_fetch:
            log.info("NOFETCH, will not be automatically updating.")

        # Actual start.
        self.get_storage()
        self.get_config()
        self.get_fetch()

        self.setup_hooks()

        sp = self.conf_dir + "/.canto_socket"
        log.info("Listening on unix socket: %s" % sp)

        try:
            if self.port < 0:
                CantoServer.__init__(self, sp, queue.Queue())
            else:
                log.info("Listening on interface %s:%d" %\
                        (self.intf, self.port))
                CantoServer.__init__(self, sp, queue.Queue(),\
                        port = self.port, interface = self.intf)
        except Exception as e:
            err = "Error: %s" % e
            print(err)
            log.error(err)
            call_hook("exit", [])
            sys.exit(-1)

        # Signal handlers kickoff after everything else is init'd

        self.alarmed = 0
        self.interrupted = 0

        signal.signal(signal.SIGALRM, self.sig_alrm)
        signal.signal(signal.SIGINT, self.sig_int)
        signal.signal(signal.SIGTERM, self.sig_int)
        signal.alarm(1)

    def check_dead_feeds(self):
        for URL in list(allfeeds.dead_feeds.keys()):
            feed = allfeeds.dead_feeds[URL]
            for item in feed.items:
                if protection.protected(item["id"]):
                    log.debug("Dead feed %s still committed." % feed.URL)
                    break
            else:
                allfeeds.really_dead(feed)

    def _reparse_config(self, originating_socket):
        self.conf.parse(False)

        if self.conf.errors:
            self.write(originating_socket, "ERRORS", self.conf.errors)
            self.conf.parse()
        else:
            self.conf.write()

        self.check_dead_feeds()
        alltags.del_old_tags()

    # Propagate config changes to watching sockets.

    # On_config_change must be prepared to have originating_socket = None for internal requests that
    # nonetheless must be propagated.

    def on_config_change(self, change, originating_socket):

        self._reparse_config(originating_socket)

        # Force check of fetching. This automatically starts the fetch. For new
        # feeds, but also takes any new settings (like rates) into account.

        self.fetch_timer = 0

        # Pretend that the sockets *other* than the ones that made the change
        # issued a CONFIGS for each of the root keys.

        for socket in self.watches["config"]:
            # Don't echo changes back to socket that made them.
            if socket != originating_socket:
                self.cmd_configs(socket, list(change.keys()))

    # Notify clients of new tags.

    def on_new_tag(self, tags):
        for socket in self.watches["new_tags"]:
            self.write(socket, "NEWTAGS", tags)

    # Propagate tag changes to watching sockets.

    def on_tag_change(self, tag):
        if tag in self.watches["tags"]:
            for socket in self.watches["tags"][tag]:
                self.write(socket, "TAGCHANGE", tag)

    # Notify clients of dead tags:

    def on_del_tag(self, tags):
        for socket in self.watches["del_tags"]:
            self.write(socket, "DELTAGS", tags)

    # If a socket dies, it's not longer watching any events and
    # revoke any protection associated with it

    def on_kill_socket(self, socket):
        while socket in self.watches["config"]:
            self.watches["config"].remove(socket)

        while socket in self.watches["new_tags"]:
            self.watches["new_tags"].remove(socket)

        while socket in self.watches["del_tags"]:
            self.watches["del_tags"].remove(socket)

        for tag in self.watches["tags"]:
            while socket in self.watches["tags"][tag]:
                self.watches["tags"][tag].remove(socket)

        if socket in list(self.socket_transforms.keys()):
            del self.socket_transforms[socket]

        protection.unprotect((socket, "auto"))
        self.check_dead_feeds()

    def queue_internal(self, cb, func, args):
        self.queue.put((cb, func, args))

    # We need to be alerted on certain events, ensure
    # we get notified about them.

    def setup_hooks(self):
        on_hook("new_tag", self.on_new_tag)
        on_hook("del_tag", self.on_del_tag)
        on_hook("config_change", self.on_config_change)
        on_hook("tag_change", self.on_tag_change)
        on_hook("kill_socket", self.on_kill_socket)

        # For plugins
        on_hook("set_configs", lambda x, y : self.queue_internal(x, self.in_setconfigs, y))
        on_hook("del_configs", lambda x, y : self.queue_internal(x, self.in_delconfigs, y))
        on_hook("get_configs", lambda x, y : self.queue_internal(x, self.in_configs, y))

    # Return list of item tuples after global transforms have
    # been performed on them.

    def apply_transforms(self, socket, tag):

        # Lambda up a function that, given an id, can tell a filter if it's
        # protected in this circumstance without allowing filters access to the
        # socket, or requiring them to know anything about the protection
        # scheme.

        filter_immune = lambda x :\
                protection.protected_by(x, (socket, "filter-immune"))

        tagobj = alltags.get_tag(tag)

        # Global transform
        if self.conf.global_transform:
            tagobj = self.conf.global_transform(tagobj, filter_immune)

        # Tag level transform
        if tag in alltags.tag_transforms and\
                alltags.tag_transforms[tag]:
            tagobj = alltags.tag_transforms[tag](tagobj, filter_immune)

        # Temporary socket transform
        if socket in self.socket_transforms and\
                self.socket_transforms[socket]:
            tagobj = self.socket_transforms[socket](tagobj, filter_immune)

        return tagobj

    # Fetch any feeds that need fetching.

    def do_fetch(self, force = False):
        self.fetch.fetch(force)
        self.fetch_timer = FETCH_CHECK_INTERVAL

    # VERSION -> X.Y

    def cmd_version(self, socket, args):
        self.write(socket, "VERSION", CANTO_PROTOCOL_VERSION)

    # PING -> PONG

    def cmd_ping(self, socket, args):
        self.write(socket, "PONG", "")

    # LISTTAGS -> [ "tag1", "tag2", .. ]
    # This makes no guarantee on order *other* than the fact that
    # maintag tags will be first, and in feed order. Following tags
    # are in whatever order the dict gives them in.

    def cmd_listtags(self, socket, args):
        r = []
        for feed in allfeeds.get_feeds():
            r.append("maintag:" + feed.name)
        for tag in alltags.get_tags():
            if tag not in r:
                r.append(tag)

        self.write(socket, "LISTTAGS", r)

    # LISTTRANSFORMS -> [ { "name" : " " } for all defined filters ]

    def cmd_listtransforms(self, socket, args):
        transforms = []
        for transform in self.conf.transforms:
            transforms.append({"name" : transform["name"]})
        self.write(socket, "LISTTRANSFORMS", transforms)


    # TRANSFORM "" -> "current socket transform"
    # TRANSFORM "string" -> set current socket transform.

    def cmd_transform(self, socket, args):
        # Clear with !args
        if not args:
            if socket in self.socket_transforms:
                del self.socket_transforms[socket]
            self.write(socket, "TRANSFORM", "")
            return

        filt = None
        try:
            filt = eval_transform(args)
        except:
            self.write(socket, "EXCEPT",\
                    "Couldn't parse transform: %s" % args)
            return

        self.socket_transforms[socket] = filt

        # Echo back on successful compilation.
        self.write(socket, "TRANSFORM", args)

    # AUTOATTR [ attrs ... ] -> Follow up each items request with
    # an attributes request for attrs.

    # This command is intended to reduce round trip time and allow
    # clients to become informative quickly by making the individual
    # story IDs unnecessary to request information about them.

    def cmd_autoattr(self, socket, args):
        self.autoattr[socket] = args

    # ITEMS [tags] -> { tag : [ ids ], tag2 : ... }

    def cmd_items(self, socket, args):
        ids = []
        response = {}

        for tag in args:
            # get_tag returns a list invariably, but may be empty.
            items = self.apply_transforms(socket, tag)

            # ITEMS must protect all given items automatically to
            # avoid instances where an item disappears before a PROTECT
            # call can be made by the client.

            protection.protect((socket, "auto"), items)

            # Divide each response into 100 items or less and dispatch them

            attr_list = []

            while len(items):
                chunk = items[:100]
                items = items[100:]

                attr_req = {}
                if socket in self.autoattr:
                    for id in chunk:
                        attr_req[id] = self.autoattr[socket][:]

                self.write(socket, "ITEMS", { tag : chunk })
                attr_list.append(attr_req)

            self.write(socket, "ITEMSDONE", {})

            for attr_req in attr_list:
                self.cmd_attributes(socket, attr_req)

    # FEEDATTRIBUTES { 'url' : [ attribs .. ] .. } ->
    # { url : { attribute : value } ... }

    def cmd_feedattributes(self, socket, args):
        r = {}
        for url in list(args.keys()):
            feed = allfeeds.get_feed(url)
            if not feed:
                continue
            r.update({ url : feed.get_feedattributes(args[url])})
        self.write(socket, "FEEDATTRIBUTES", r)

    # ATTRIBUTES { id : [ attribs .. ] .. } ->
    # { id : { attribute : value } ... }

    def cmd_attributes(self, socket, args):
        ret = {}
        feeds = allfeeds.items_to_feeds(list(args.keys()))
        for f in feeds:
            ret.update(f.get_attributes(feeds[f], args))

        self.write(socket, "ATTRIBUTES", ret)

    # SETATTRIBUTES { id : { attribute : value } ... } -> None

    def cmd_setattributes(self, socket, args):

        feeds = allfeeds.items_to_feeds(list(args.keys()))
        for f in feeds:
            f.set_attributes(feeds[f], args)

        tags = alltags.items_to_tags(list(args.keys()))
        for t in tags:
            call_hook("tag_change", [ t ])

    # CONFIGS [ "top_sec", ... ] -> { "top_sec" : full_value }

    # Internal

    def in_configs(self, args):
        if args:
            ret = {}
            for topsec in args:
                if topsec in self.conf.json:
                    ret[topsec] = self.conf.json[topsec]
        else:
            ret = self.conf.json
        return ret

    # External

    def cmd_configs(self, socket, args):
        ret = self.in_configs(args)
        self.write(socket, "CONFIGS", ret)

    # Please NOTE that SET and DEL do no locking, no revision tracking
    # whatsoever. There's no forcing clients to only make changes to
    # configurations that they've already acknowledged.

    # What I *have* done is harden the data structures so that with a little
    # care, clients can do non-destructive changes to the config. For example,
    # list objects in the config can have items added from multiple clients,
    # without each client having to know it's complete contents. So two feeds
    # added by different clients will still race (you can't tell which order
    # the feeds will be in in relation to each other), but one add won't blow
    # away the other.

    # The bottom line though is that I don't want to implement any sort of
    # config rejection capability (i.e. conflict handling) or lock /
    # synchronization mechanism (on *either* the daemon or client side) just to
    # allow users to do two diametrically opposed config settings in two
    # different clients at the exact same time.

    # It's just not worth it.

    # SETCONFIGS { "key" : "value", ...}

    def in_setconfigs(self, args):
        self.cmd_setconfigs(None, args)
        return self.conf.json

    def cmd_setconfigs(self, socket, args):

        self.conf.merge(args.copy())

        call_hook("config_change", [args, socket])

    # DELCONFIGS { "key" : "DELETE", ...}

    def in_delconfigs(self, args):
        cmd_delconfigs(None, args)
        return self.conf.json

    def cmd_delconfigs(self, socket, args):

        self.conf.delete(args.copy())

        call_hook("config_change", [args, socket])

    # WATCHCONFIGS

    def cmd_watchconfigs(self, socket, args):
        self.watches["config"].append(socket)

    # WATCHNEWTAGS

    def cmd_watchnewtags(self, socket, args):
        self.watches["new_tags"].append(socket)

    # WATCHDELTAGS

    def cmd_watchdeltags(self, socket, args):
        self.watches["del_tags"].append(socket)

    # WATCHTAGS [ "tag", ... ]

    def cmd_watchtags(self, socket, args):
        for tag in args:
            log.debug("socket %s watching tag %s" % (socket, tag))
            if tag in self.watches["tags"]:
                self.watches["tags"][tag].append(socket)
            else:
                self.watches["tags"][tag] = [socket]

    # PROTECT { "reason" : [ id, ... ], ... }

    def cmd_protect(self, socket, args):
        for reason in args:
            protection.protect((socket, reason), args[reason])

    # UNPROTECT { "reason" : [ id, ... ], ... }

    def cmd_unprotect(self, socket, args):
        for reason in args:
            for id in args[reason]:
                protection.unprotect_one((socket, reason), id)

    # UPDATE {}

    # Note that this is intended to allow clients to take manual
    # control when canto is started with --nofetch and doesn't
    # override rates or any other factors in updating.

    def cmd_update(self, socket, args):
        self.do_fetch()

    # FORCEUPDATE {}

    # This command, on the other hand, *will* force the timers.

    def cmd_forceupdate(self, socket, args):
        self.do_fetch(True)

    # The workhorse that maps all requests to their handlers.
    def run(self):
        log.debug("Beginning to serve...")
        call_hook("serving", [])
        while 1:
            try:
                if self.interrupted:
                    log.info("Interrupted. Exiting.")
                    return

                # If we've received a SIGALARM, we switch to a shorter timeout
                # until we've cleared the queue and get an exception, which
                # will let us handle the alarm.

                # It really sucks that we don't get signals will in a Queue.get
                # =(

                if self.alarmed:
                    r = self.queue.get(True, 0.1)
                else:
                    r = self.queue.get(True, 1)

                log.debug("!!! %s" % (r,))

                # 3-tuple = internal command
                if len(r) == 3:
                    cb, func, args = r
                    r = func(args)
                    if cb:
                        cb(r)
                    continue

                # 2-tuple = external command
                else:
                    socket, (cmd, args) = r

            except queue.Empty:
                pass
            else:
                if cmd == "DIE":
                    log.info("Received DIE.")
                    return

                if cmd == "NEWCONN":
                    self.accept_conn(socket)
                    continue

                cmdf = "cmd_" + cmd.lower()
                if hasattr(self, cmdf):
                    func = getattr(self, cmdf)
                    try:
                        func(socket, args)
                    except Exception as e:
                        tb = "".join(traceback.format_exc())
                        self.write(socket, "EXCEPT", tb)
                        log.error("Protocol exception:")
                        log.error("\n" + tb)
                else:
                    log.info("Got unknown command: %s" % (cmd))

                # Give priority to waiting requests, try for
                # another one instead of doing feed processing in between.
                continue

            self.alarmed = 0
            call_hook("work_done", [])

            # Clean up any dead connection threads.

            self.no_dead_conns()

            # Process any possible feed updates.

            self.fetch.process()

            # Decrement all timers

            self.fetch_timer -= 1
            self.trim_timer -= 1

            # Check whether feeds need to be updated and fetch
            # them if necessary.

            if self.fetch_timer <= 0 and not self.no_fetch:
                self.do_fetch()

            # Trim the database file.

            if self.trim_timer <= 0:
                self.shelf.trim()
                self.trim_timer = TRIM_INTERVAL

    # This function parses and validates all of the command line arguments.
    def args(self):
        try:
            optlist = getopt.getopt(sys.argv[1:], 'D:vp:a:nV',\
                    ["dir=", "port=", "address=", "nofetch", "nowb"])[0]
        except getopt.GetoptError as e:
            log.error("Error: %s" % e.msg)
            return -1

        self.conf_dir = os.path.expanduser("~/.canto-ng/")

        for opt, arg in optlist:
            # -D base configuration directory. Highest priority.
            if opt in ["-D", "--dir"]:
                self.conf_dir = os.path.expanduser(arg)
                self.conf_dir = os.path.realpath(self.conf_dir)

            # -v increase verbosity
            elif opt in ["-v"]:
                self.verbosity += 1

            elif opt in ["-p", "--port"]:
                try:
                    self.port = int(arg)
                    if self.port < 0:
                        raise Exception
                except:
                    log.error("Error: Port must be >0 integer.")
                    return -1

            elif opt in ["-a", "--address"]:
                self.intf = arg

            elif opt in ["-n", "--nofetch"]:
                self.no_fetch = True

            elif opt in ["--nowb"]:
                self.writeback = False

            elif opt in ['-V']:
                print("canto-daemon " + version)
                return 1

        return 0

    def sig_alrm(self, a, b):
        self.alarmed = 1
        signal.alarm(1)

    def sig_int(self, a, b):
        self.interrupted = 1

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
            except Exception as e:
                log.error("Exception making %s : %s" % (self.conf_dir, e))
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
        except IOError as e:
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
        self.shelf = CantoShelf(self.feed_path, self.writeback)

    # Bring up config, the only errors possible at this point will
    # be fatal and handled lower in CantoConfig.

    def get_config(self):
        self.conf = CantoConfig(self.conf_path, self.shelf)
        self.conf.parse()
        if self.conf.errors:
            print("ERRORS:")
            for key in list(self.conf.errors.keys()):
                for value, error in self.conf.errors[key]:
                    s = "\t%s -> %s: %s" % (key, value, error)
                    print(encoder(s))

            sys.exit(-1)

    def get_fetch(self):
        self.fetch = CantoFetch(self.shelf)

    def start(self):
        try:
            self.init()
            self.run()
            log.info("Exiting cleanly.")

        # Cleanly shutdown on ^C.
        except KeyboardInterrupt:
            pass

        # Pretty print any non-Keyboard exceptions.
        except Exception as e:
            tb = traceback.format_exc()
            log.error("Exiting on exception:")
            log.error("\n" + "".join(tb))

        call_hook("exit", [])
        self.exit()
        self.pid_unlock()
        sys.exit(0)
