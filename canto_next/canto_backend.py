# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# This Backend class is the core of the daemon's specific protocol.

CANTO_PROTOCOL_VERSION = 0.9

from .feed import allfeeds, wlock_all, stop_feeds, rlock_feed_objs, runlock_feed_objs
from .encoding import encoder
from .server import CantoServer
from .config import config, parse_locks, parse_unlocks
from .storage import CantoShelf
from .fetch import CantoFetch
from .hooks import on_hook, call_hook
from .tag import alltags
from .transform import eval_transform
from .plugins import PluginHandler, Plugin, try_plugins, set_program
from .rwlock import alllocks, write_lock, read_lock
from .locks import *

import traceback
import logging
import signal
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

class DaemonBackendPlugin(Plugin):
    pass

# Index threads and the main thread no longer take multiple locks at once. The
# cmd_* functions in CantoBackend only need to worry about deadlocking with
# each other.

class CantoBackend(PluginHandler, CantoServer):
    def __init__(self):

        # Nothing referenced before try_plugins should be
        # pluggable.

        self.plugin_attrs = {}

        # Shelf for feeds:
        self.fetch = None
        self.fetch_manual = False
        self.fetch_force = False

        # Whether fetching is inhibited.
        self.no_fetch = False

        self.watches = { "new_tags" : [],
                         "del_tags" : [],
                         "config" : [],
                         "tags" : {} }

        self.autoattr = {}

        # Per socket transforms.
        self.socket_transforms = {}

        self.shelf = None

        # No bad arguments.
        version = "canto-daemon " + REPLACE_VERSION + " " + GIT_HASH
        optl = self.common_args("nhc:",["nofetch","help","cache="], version)
        if optl == -1:
            sys.exit(-1)

        if self.args(optl):
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
        log.info(version)

        if self.verbosity:
            rootlog = logging.getLogger()
            rootlog.setLevel(max(rootlog.level - 10 * self.verbosity,0))
            log.info("verbosity = %d" % self.verbosity)

        log.info("conf_dir = %s" % self.conf_dir)

        # Evaluate any plugins
        set_program("canto-daemon")
        try_plugins(self.conf_dir, self.plugin_default, self.disabled_plugins,
                self.enabled_plugins)

        PluginHandler.__init__(self)

        self.plugin_class = DaemonBackendPlugin
        self.update_plugin_lookups()

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
                        (self.addr, self.port))
                CantoServer.__init__(self, self.sfile, self.socket_command,\
                        port = self.port, interface = self.addr)
        except Exception as e:
            err = "Error: %s" % e
            print(err)
            log.error(err)
            call_hook("daemon_exit", [])
            sys.exit(-1)

        # Signal handlers kickoff after everything else is init'd

        self.interrupted = 0

        signal.signal(signal.SIGINT, self.sig_int)
        signal.signal(signal.SIGTERM, self.sig_int)
        signal.signal(signal.SIGUSR1, self.sig_usr)

        self.start()

    def on_config_change(self, change, originating_socket):

        config.parse(False, change)

        log.debug("config.errors = %s", config.errors)

        if config.errors:
            self.write(originating_socket, "ERRORS", config.errors)
            config.parse()

            # No changes actually realized, bail
            return
        else:
            config.write()

        # Kill feeds that haven't been re-instantiated.
        allfeeds.all_parsed()

        # Force check of fetching. This automatically starts the fetch. For new
        # feeds, but also takes any new settings (like rates) into account.

        self.fetch_force = True

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

    # If a socket dies, it's no longer watching any events.

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

    @read_lock(feed_lock)
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
        for transform in config.transforms:
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
                    log.debug("Unsetting socket transform %s:%s", socket, key)
                    del self.socket_transforms[socket][key]
                continue

            log.debug("Setting socket transform: %s:%s = %s", socket, key, filt)
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

    @read_lock(attr_lock)
    @read_lock(feed_lock)
    def _apply_socktrans(self, socket, tag):
        feeds = allfeeds.items_to_feeds(tag)
        rlock_feed_objs(feeds)
        socktran_lock.acquire_read()
        try:

            for filt in self.socket_transforms[socket]:
                tag = self.socket_transforms[socket][filt](tag)
        finally:
            socktran_lock.release_read()
            runlock_feed_objs(feeds)
        return tag

    def cmd_items(self, socket, args):
        ids = []
        response = {}

        for tag in args:
            items = alltags.get_tag(tag)

            if socket in self.socket_transforms:
                items = self._apply_socktrans(socket, items)

            attr_list = []

            if len(items) == 0:
                self.write(socket, "ITEMS", { tag : [] })
            else:
                attr_req = {}
                if socket in self.autoattr:
                    for id in items:
                        attr_req[id] = self.autoattr[socket][:]
                    attr_list.append(attr_req)

                self.write(socket, "ITEMS", { tag : items })

            self.write(socket, "ITEMSDONE", {})

            for attr_req in attr_list:
                self.cmd_attributes(socket, attr_req)

    # ATTRIBUTES { id : [ attribs .. ] .. } ->
    # { id : { attribute : value } ... }

    # Hold feed_lock so that get_attributes won't fail on a missing feed, but
    # items_to_feeds can still throw an exception if attributes requests come
    # in for items from removed feeds.

    @read_lock(feed_lock)
    def cmd_attributes(self, socket, args):
        ret = {}
        feeds = allfeeds.items_to_feeds(list(args.keys()))
        for f in feeds:
            ret.update(f.get_attributes(feeds[f], args))

        self.write(socket, "ATTRIBUTES", ret)

    # SETATTRIBUTES { id : { attribute : value } ... } -> None

    @read_lock(feed_lock)
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
                if topsec in config.json:
                    ret[topsec] = config.json[topsec]
        else:
            ret = config.json

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
        return config.json

    def cmd_setconfigs(self, socket, args):
        parse_locks()

        config.merge(args.copy())

        # config_change handles it's own locking
        call_hook("daemon_config_change", [args, socket])

        parse_unlocks()

    # DELCONFIGS { "key" : "DELETE", ...}

    def in_delconfigs(self, args):
        self.cmd_delconfigs(None, args)
        return config.json

    def cmd_delconfigs(self, socket, args):
        parse_locks()

        config.delete(args.copy())

        # config_change handles it's own locking
        call_hook("daemon_config_change", [args, socket])

        parse_unlocks()

    # WATCHCONFIGS

    @write_lock(watch_lock)
    def cmd_watchconfigs(self, socket, args):
        if socket not in self.watches["config"]:
            self.watches["config"].append(socket)

    # WATCHNEWTAGS

    @write_lock(watch_lock)
    def cmd_watchnewtags(self, socket, args):
        if socket not in self.watches["new_tags"]:
            self.watches["new_tags"].append(socket)

    # WATCHDELTAGS

    @write_lock(watch_lock)
    def cmd_watchdeltags(self, socket, args):
        if socket not in self.watches["del_tags"]:
            self.watches["del_tags"].append(socket)

    # WATCHTAGS [ "tag", ... ]

    @write_lock(watch_lock)
    def cmd_watchtags(self, socket, args):
        for tag in args:
            log.debug("socket %s watching tag %s", socket, tag)
            if tag in self.watches["tags"]:
                if socket not in self.watches["tags"][tag]:
                    self.watches["tags"][tag].append(socket)
            else:
                self.watches["tags"][tag] = [socket]

    # UPDATE {}

    # Note that this is intended to allow clients to take manual
    # control when canto is started with --nofetch and doesn't
    # override rates or any other factors in updating.

    def cmd_update(self, socket, args):
        self.fetch_manual = True
        self.fetch_force = False

    # FORCEUPDATE {}

    # This command, on the other hand, *will* force the timers.

    def cmd_forceupdate(self, socket, args):
        self.fetch_manual = True
        self.fetch_force = True

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
            else:
                log.info("Got unknown command: %s" % (cmd))

    def internal_command(self, cb, func, args):
        r = func(args)
        if cb:
            cb(r)

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
            self.fetch.reap()

            # Check whether feeds need to be updated and fetch
            # them if necessary.

            if (not self.no_fetch or self.fetch_manual):
                self.fetch.fetch(self.fetch_force, False)

                self.fetch_manual = False
                self.fetch_force = False

            call_hook("daemon_end_loop", [])

            time.sleep(1)

    # Shutdown cleanly

    def cleanup(self):
        # Stop feeds, will cause feed.index() threads to bail without
        # Messing with the disk.

        stop_feeds()

        # Grab locks to keep any other write usage from happening.

        wlock_all()

        self.shelf.close()

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

    def print_help(self):
        print("USAGE: canto-daemon [options]")
        print("\t-h/--help\tThis help")
        print("\t-V/--version\tPrint version")
        print("\t-v/\t\tVerbose logging (for debug)")
        print("\t-D/--dir <dir>\tSet configuration directory.")
        print("\t-n/--nofetch\tJust serve content, don't fetch new content.")
        print("\n\nPlugin control\n")
        print("\t--noplugins\t\t\t\tDisable plugins")
        print("\t--enableplugins 'plugin1 plugin2...'\tEnable single plugins (overrides --noplugins)")
        print("\t--disableplugins 'plugin1 plugin2...'\tDisable single plugins")
        print("\nNetwork control\n")
        print("NOTE: These should be used in conjunction with SSH port forwarding to be secure\n")
        print("\t-a/--address <IP>\tBind to interface with this address")
        print("\t-p/--port <port>\tBind to this port")

    # This function parses and validates all of the command line arguments.
    def args(self, optlist):
        for opt, arg in optlist:
            if opt in ["-n", "--nofetch"]:
                self.no_fetch = True
            elif opt in ['-h', '--help']:
                self.print_help()
                sys.exit(0)
        return 0

    def sig_int(self, a, b):
        log.info("Received INT")
        self.interrupted = 1

    def sig_usr(self, a, b):
        import threading
        import gc

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

        self.shelf.sync()
        gc.collect()

        # If we've got pympler installed, output a summary of memory usage.

        try:
            from pympler import summary, muppy
            summary.print_(summary.summarize(muppy.get_objects()))
        except:
            pass

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
        self.shelf = CantoShelf(self.feed_path)

    # Bring up config, the only errors possible at this point will
    # be fatal and handled lower in CantoConfig.

    def get_config(self):
        config.init(self.conf_path, self.shelf)
        config.parse()
        if config.errors:
            print("ERRORS:")
            for key in list(config.errors.keys()):
                for value, error in config.errors[key]:
                    s = "\t%s -> %s: %s" % (key, value, error)
                    print(encoder(s))

            sys.exit(-1)

    def get_fetch(self):
        self.fetch = CantoFetch(self.shelf)

    def remove_socketfile(self):
        os.unlink(self.sfile)

    def start(self):
        try:
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
