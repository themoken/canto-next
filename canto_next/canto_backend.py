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

from .feed import allfeeds, wlock_feeds, rlock_feeds, wlock_all, wunlock_all, rlock_all, runlock_all, stop_feeds
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
from .rwlock import alllocks, write_lock, read_lock
from .locks import *

import traceback
import logging
import signal
import getopt
import fcntl
import errno
import time
import sys
import os

# By default this will log to stderr.
logging.basicConfig(
        format = "%(asctime)s : %(name)s -> %(message)s",
        datefmt = "%H:%M:%S",
        level = logging.INFO
)

log = logging.getLogger("CANTO-DAEMON")

FETCH_CHECK_INTERVAL = 60
TRIM_INTERVAL = 300

# x.lock is a specific feed's lock
# x.locks are all feed's locks
#
# Index threads take
#   x.lock (w) -> protect_lock (r)
#              \> tag_lock (w)
#
# (meaning that it holds x.lock, but takes protect and tag locks serially)
#
# So, if any command (in this file) needs to take feed_lock and x.locks first
#
# Every other threaded lock taker is going to come through CantoBackend, so the
# lock order must be the same. Between all cmd_ functions.
#
# Fortunately, this means we can do locks alphabetically.
#
# Another caveat is that commands that call each other need to hold all the
# locks at the outset. For example, cmd_items calls cmd_attributes (to handle
# automatic attributes), so it needs to hold the feed and protect locks, even
# if it didn't have to otherwise.

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

        self.sfile = self.conf_dir + "/.canto_socket"
        log.info("Listening on unix socket: %s" % self.sfile)

        try:
            if self.port < 0:
                CantoServer.__init__(self, self.sfile, self.socket_command)
            else:
                log.info("Listening on interface %s:%d" %\
                        (self.intf, self.port))
                CantoServer.__init__(self, self.sfile, self.socket_command,\
                        port = self.port, interface = self.intf)
        except Exception as e:
            err = "Error: %s" % e
            print(err)
            log.error(err)
            call_hook("daemon_exit", [])
            sys.exit(-1)

        # Signal handlers kickoff after everything else is init'd

        self.interrupted = 0

        signal.signal(signal.SIGINT, self.sig_int)
        signal.signal(signal.SIGTERM, self.sig_term)
        signal.signal(signal.SIGUSR1, self.sig_usr)

    def _check_dead_feeds(self):
        for URL in list(allfeeds.dead_feeds.keys()):
            feed = allfeeds.dead_feeds[URL]
            for item in feed.items:
                if protection.protected(item["id"]):
                    log.debug("Dead feed %s still committed." % feed.URL)
                    break
            else:
                allfeeds.really_dead(feed)

    @wlock_feeds
    @read_lock(protect_lock)
    def check_dead_feeds(self):
        self._check_dead_feeds()

    def _reparse_config(self, originating_socket):
        self.conf.parse(False)

        if self.conf.errors:
            self.write(originating_socket, "ERRORS", self.conf.errors)
            self.conf.parse()
        else:
            self.conf.write()

        self._check_dead_feeds()

        alltags.del_old_tags()

    # Propagate config changes to watching sockets.

    # On_config_change must be prepared to have originating_socket = None for
    # internal requests that nonetheless must be propagated.

    # This is invoked by set or del configs, which holds write locks on
    # everything needed, config (for reparse/in_configs), and watch.

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
                self.in_configs(list(change.keys()), socket)

    # Notify clients of new tags.

    @read_lock(watch_lock)
    def on_new_tag(self, tags):
        for socket in self.watches["new_tags"]:
            self.write(socket, "NEWTAGS", tags)

    # Propagate tag changes to watching sockets.

    @read_lock(watch_lock)
    def on_tag_change(self, tag):
        if tag in self.watches["tags"]:
            for socket in self.watches["tags"][tag]:
                self.write(socket, "TAGCHANGE", tag)

    # Notify clients of dead tags:

    @read_lock(watch_lock)
    def on_del_tag(self, tags):
        for socket in self.watches["del_tags"]:
            self.write(socket, "DELTAGS", tags)

    # If a socket dies, it's not longer watching any events and
    # revoke any protection associated with it

    @wlock_feeds
    @write_lock(protect_lock)
    @write_lock(socktran_lock)
    @write_lock(watch_lock)
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
        self._check_dead_feeds()

    # We need to be alerted on certain events, ensure
    # we get notified about them.

    def setup_hooks(self):
        on_hook("daemon_new_tag", self.on_new_tag)
        on_hook("daemon_del_tag", self.on_del_tag)
        on_hook("daemon_config_change", self.on_config_change)
        on_hook("daemon_tag_change", self.on_tag_change)
        on_hook("server_kill_socket", self.on_kill_socket)

        # For plugins
        on_hook("daemon_set_configs", lambda x, y : self.internal_command(x, self.in_setconfigs, y))
        on_hook("daemon_del_configs", lambda x, y : self.internal_command(x, self.in_delconfigs, y))
        on_hook("daemon_get_configs", lambda x, y : self.internal_command(x, self.in_configs, y))

    # Return list of item tuples after global transforms have
    # been performed on them.

    def apply_transforms(self, socket, tag):

        # Lambda up a function that, given an id, can tell a filter if it's
        # protected in this circumstance without allowing filters access to the
        # socket, or requiring them to know anything about the protection
        # scheme.

        filter_immune = lambda x :\
                protection.protected_by(x, (socket, "filter-immune"))

        # Lock the feeds so we don't lose any items. We don't want transforms
        # to have to deal with ids disappearing from feeds.

        # Because we hold tag / protect write, we know that no more feeds can
        # start indexing, so taking the lock just means we're making sure none
        # of them are in progress.

        tagobj = alltags.get_tag(tag)

        f = allfeeds.items_to_feeds(tagobj)

        # Global transform
        if self.conf.global_transform:
            tagobj = self.conf.global_transform(tagobj, filter_immune)

        # Tag level transform
        if tag in alltags.tag_transforms and\
                alltags.tag_transforms[tag]:
            tagobj = alltags.tag_transforms[tag](tagobj, filter_immune)

        # Socket transforms ANDed together.
        if socket in self.socket_transforms:
            for filt in self.socket_transforms[socket]:
                tagobj = self.socket_transforms[socket][filt](tagobj, filter_immune)

        return tagobj

    # Fetch any feeds that need fetching.

    @read_lock(feed_lock)
    @write_lock(fetch_lock)
    def do_fetch(self, force = False):
        self.fetch.fetch(force, False)
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

    @rlock_feeds
    @read_lock(tag_lock)
    def cmd_listtags(self, socket, args):
        r = []
        for feed in allfeeds.get_feeds():
            r.append("maintag:" + feed.name)
        for tag in alltags.get_tags():
            if tag not in r:
                r.append(tag)

        self.write(socket, "LISTTAGS", r)

    # LISTTRANSFORMS -> [ { "name" : " " } for all defined filters ]

    @read_lock(config_lock)
    def cmd_listtransforms(self, socket, args):
        transforms = []
        for transform in self.conf.transforms:
            transforms.append({"name" : transform["name"]})
        self.write(socket, "LISTTRANSFORMS", transforms)


    # TRANSFORM {} -> return current socket transform, with names instead of
    # actual filt objects.
    # TRANSFORM {"string":"transform"} -> set a socket transform
    # TRANSFORM {"string": None } -> un set a socket transform

    @write_lock(socktran_lock)
    def cmd_transform(self, socket, args):
        if not args:
            if socket in self.socket_transforms:
                str_dict = {}
                for filt in self.socket_transforms[socket]:
                    str_dict[filt] = str(self.socket_transforms[socket][filt])
                self.write(socket, "TRANSFORM", str_dict)
            else:
                self.write(socket, "TRANSFORM", {})
            return

        if socket not in self.socket_transforms:
            self.socket_transforms[socket] = {}

        for key in args:
            # Unset beforehand means query.
            if not args[key]:
                if key in self.socket_transforms[socket]:
                    self.write(socket, "TRANSFORM", { key : str(self.socket_transforms[socket][key])})
                else:
                    self.write(socket, "TRANSFORM", { key : "None" })
                continue

            filt = None
            try:
                filt = eval_transform(args[key])
            except Exception as e:
                self.write(socket, "EXCEPT",\
                        "Couldn't parse transform: %s\n%s" % (args[key], e))
                continue

            if filt == None:
                if key in self.socket_transforms[socket]:
                    log.debug("Unsetting socket transform %s:%s" % (socket, key))
                    del self.socket_transforms[socket][key]
                continue

            log.debug("Setting socket transform: %s:%s = %s" % (socket, key, filt))
            self.socket_transforms[socket][key] = filt

    # AUTOATTR [ attrs ... ] -> Follow up each items request with
    # an attributes request for attrs.

    # This command is intended to reduce round trip time and allow
    # clients to become informative quickly by making the individual
    # story IDs unnecessary to request information about them.

    # Hold attr_lock just to keep cmd_item from trying to use autoattr
    @write_lock(attr_lock)
    def cmd_autoattr(self, socket, args):
        self.autoattr[socket] = args

    # ITEMS [tags] -> { tag : [ ids ], tag2 : ... }

    @rlock_feeds # For _cmd_attributes
    @read_lock(attr_lock)
    @read_lock(config_lock)
    @write_lock(protect_lock)
    @read_lock(socktran_lock)
    @read_lock(tag_lock)
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
                self._cmd_attributes(socket, attr_req)

    # FEEDATTRIBUTES { 'url' : [ attribs .. ] .. } ->
    # { url : { attribute : value } ... }

    @rlock_feeds
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

    # This is called with appropriate locks from cmd_items

    def _cmd_attributes(self, socket, args):
        ret = {}
        feeds = allfeeds.items_to_feeds(list(args.keys()))
        for f in feeds:
            ret.update(f.get_attributes(feeds[f], args))

        self.write(socket, "ATTRIBUTES", ret)

    @rlock_feeds
    def cmd_attributes(self, socket, args):
        self._cmd_attributes(socket, args)

    # SETATTRIBUTES { id : { attribute : value } ... } -> None

    @wlock_feeds
    @write_lock(attr_lock)
    @write_lock(tag_lock)
    def cmd_setattributes(self, socket, args):

        feeds = allfeeds.items_to_feeds(list(args.keys()))
        for f in feeds:
            f.set_attributes(feeds[f], args)

        tags = alltags.items_to_tags(list(args.keys()))
        for t in tags:
            call_hook("daemon_tag_change", [ t ])

    # CONFIGS [ "top_sec", ... ] -> { "top_sec" : full_value }

    # Internally, called only by functions that hold read or write on
    # config_lock

    def in_configs(self, args, socket=None):
        if args:
            ret = {}
            for topsec in args:
                if topsec in self.conf.json:
                    ret[topsec] = self.conf.json[topsec]
        else:
            ret = self.conf.json

        if socket:
            self.write(socket, "CONFIGS", ret)
        return ret

    # External, needs to grab lock.

    @read_lock(config_lock)
    def cmd_configs(self, socket, args):
        ret = self.in_configs(args, socket)

    # SETCONFIGS { "key" : "value", ...}

    def in_setconfigs(self, args):
        self.cmd_setconfigs(None, args)
        return self.conf.json

    @write_lock(feed_lock)
    @write_lock(config_lock)
    @read_lock(protect_lock)
    @write_lock(tag_lock)
    @read_lock(watch_lock)
    def cmd_setconfigs(self, socket, args):

        self.conf.merge(args.copy())

        # config_change handles it's own locking
        call_hook("daemon_config_change", [args, socket])

    # DELCONFIGS { "key" : "DELETE", ...}

    def in_delconfigs(self, args):
        cmd_delconfigs(None, args)
        return self.conf.json

    @write_lock(feed_lock)
    @write_lock(config_lock)
    @read_lock(protect_lock)
    @write_lock(tag_lock)
    @read_lock(watch_lock)
    def cmd_delconfigs(self, socket, args):

        self.conf.delete(args.copy())

        # config_change handles it's own locking
        call_hook("daemon_config_change", [args, socket])

    # WATCHCONFIGS

    @write_lock(watch_lock)
    def cmd_watchconfigs(self, socket, args):
        self.watches["config"].append(socket)

    # WATCHNEWTAGS

    @write_lock(watch_lock)
    def cmd_watchnewtags(self, socket, args):
        self.watches["new_tags"].append(socket)

    # WATCHDELTAGS

    @write_lock(watch_lock)
    def cmd_watchdeltags(self, socket, args):
        self.watches["del_tags"].append(socket)

    # WATCHTAGS [ "tag", ... ]

    @write_lock(watch_lock)
    def cmd_watchtags(self, socket, args):
        for tag in args:
            log.debug("socket %s watching tag %s" % (socket, tag))
            if tag in self.watches["tags"]:
                self.watches["tags"][tag].append(socket)
            else:
                self.watches["tags"][tag] = [socket]

    # PROTECT { "reason" : [ id, ... ], ... }

    @write_lock(protect_lock)
    def cmd_protect(self, socket, args):
        for reason in args:
            protection.protect((socket, reason), args[reason])

    # UNPROTECT { "reason" : [ id, ... ], ... }

    @write_lock(protect_lock)
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

    def socket_command(self, socket, data):
        cmd, args = data

        if cmd == "DIE":
            log.info("Received DIE.")
            self.interrupted = True
        else:
            cmdf = "cmd_" + cmd.lower()
            if hasattr(self, cmdf):
                func = getattr(self, cmdf)

                call_hook("daemon_pre_" + cmd.lower(), [socket, args])

                try:
                    func(socket, args)
                except Exception as e:
                    tb = "".join(traceback.format_exc())
                    self.write(socket, "EXCEPT", tb)
                    log.error("Protocol exception:")
                    log.error("\n" + tb)

                call_hook("daemon_post_" + cmd.lower(), [socket, args])

                call_hook("daemon_work_done", [])
            else:
                log.info("Got unknown command: %s" % (cmd))

    def internal_command(self, cb, func, args):
        r = func(args)
        if cb:
            cb(r)

        call_hook("daemon_work_done", [])

    def run(self):

        # Start fetch threads to load from disk. No need for locking as we
        # haven't started any threads yet
        self.fetch.fetch(True, True)

        log.debug("Beginning to serve...")
        call_hook("daemon_serving", [])
        while 1:
            if self.interrupted:
                log.info("Interrupted. Exiting.")
                return

            # Clean up any dead connection threads.
            self.no_dead_conns()

            # Clean up any threads done updating.
            fetch_lock.acquire_write()
            self.fetch.reap()
            fetch_lock.release_write()

            # Decrement all timers

            self.fetch_timer -= 1
            self.trim_timer -= 1

            # Check whether feeds need to be updated and fetch
            # them if necessary.

            if self.fetch_timer <= 0 and not self.no_fetch:
                self.do_fetch()

            # Trim the database file.

            if self.trim_timer <= 0:
                wlock_all()
                self.shelf.trim()
                wunlock_all()
                self.trim_timer = TRIM_INTERVAL

            time.sleep(1)

    # Shutdown cleanly

    def cleanup(self):
        # Stop feeds, will cause feed.index() threads to bail without
        # Messing with the disk.

        stop_feeds()

        # Grab locks to keep any other write usage from happening.

        wlock_all()

        # Now that we can be sure no commands or fetches are occuring, call
        # daemon_exit, which will cause the db to sync/trim/close.

        call_hook("daemon_exit", [])

        # The rest of this is bonus, the important part is to protect the disk.
        log.debug("DB shutdown.")

        # Force all connection threads to end.

        self.exit()

        # Wait for all fetches to end.

        self.fetch.reap(True)

        # Delete the socket file, so it can only be used when we're actually
        # listening.

        self.remove_socketfile()

        # Unlock the pidfile so another daemon could take over. Probably don't
        # have to do this since we're about to sys.exit anyway, but why not.

        self.pid_unlock()

        log.info("Exiting cleanly.")

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

    # SIGINT, take our time, exit cleanly

    def sig_int(self, a, b):
        log.info("Received INT")
        self.interrupted = 1

    # SIGTERM, get the fuck out quick

    def sig_term(self, a, b):
        log.info("Received TERM")
        self.cleanup()
        sys.exit(0)

    def sig_usr(self, a, b):
        import threading
        held_locks = {}
        code = {}
        curthreads = threading.enumerate()

        for threadId, stack in sys._current_frames().items():
            name = str(threadId)
            for ct in curthreads:
                if ct.ident == threadId:
                    name = ct.name

            code[name] = ["NAME: %s" % name]
            for filename, lineno, fname, line in traceback.extract_stack(stack):
                code[name].append('FILE: "%s", line %d, in %s' % (filename, lineno, fname))
                if line:
                    code[name].append("  %s" % (line.strip()))

            held_locks[name] = ""
            for lock in alllocks:
                if lock.writer_id == threadId:
                    held_locks[name] += ("%s(w)" % lock.name)
                    continue
                for reader_id, reader_stack in lock.reader_stacks:
                    if reader_id == threadId:
                        held_locks[name] += ("%s(r)" % lock.name)

        for k in code:
            log.info('\n\nLOCKS: %s \n%s' % (held_locks[k], '\n'.join(code[k])))

        log.info("\n\nSTACKS:")
        for lock in alllocks:
            for (reader_id, reader_stack) in lock.reader_stacks:
                log.info("Lock %s (%s readers)" % (lock.name, lock.readers))
                log.info("Lock reader (thread %s):" % (reader_id,))
                log.info(''.join(reader_stack))

            for writer_stack in lock.writer_stacks:
                log.info("Lock %s (%s readers)" % (lock.name, lock.readers))
                log.info("Lock writer (thread %s):" % (lock.writer_id,))
                log.info(''.join(writer_stack))

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

    @write_lock(feed_lock) # Hold this to make config add_feed happy
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

    def remove_socketfile(self):
        os.unlink(self.sfile)

    def start(self):
        try:
            self.init()
            self.run()

        # Cleanly shutdown on ^C.
        except KeyboardInterrupt:
            pass

        # Pretty print any non-Keyboard exceptions.
        except Exception as e:
            tb = traceback.format_exc()
            log.error("Exiting on exception:")
            log.error("\n" + "".join(tb))

        self.cleanup()
        sys.exit(0)
