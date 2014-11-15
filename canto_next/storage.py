# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2014 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .feed import wlock_feeds
from .hooks import on_hook, call_hook

import threading
import traceback
import logging
import shelve
import time
import dbm
import sys
import os

log = logging.getLogger("SHELF")

CACHE_OFF = 0
CACHE_ON_CONNS = 1
CACHE_ALWAYS = 2

class CantoShelf():
    def __init__(self, filename, caching):
        self.filename = filename
        self.caching = caching

        self.index = []
        self.cache = {}

        self.has_conns = False
        self.open()

        if self.caching == CACHE_ON_CONNS:
            on_hook("server_first_connection", self.on_first_conn)
            on_hook("server_no_connections", self.on_no_conns)

    @wlock_feeds
    def on_first_conn(self):
        log.debug("Heating cache.")

        self.index = []
        for item in self.shelf:
            self.cache[item] = self.shelf[item]
            self.index.append(item)

        self.has_conns = True

    def on_no_conns(self):
        log.debug("Killing cache.")
        self.has_conns = False
        self.sync()

    def check_control_data(self):
        if "control" not in self.shelf:
            self.shelf["control"] = {}

        for ctrl_field in ["canto-modified","canto-user-modified"]:
            if ctrl_field not in self.shelf["control"]:
                self.shelf["control"][ctrl_field] = 0

    @wlock_feeds
    def open(self):
        call_hook("daemon_db_open", [self.filename])

        mode = 'c'
        if dbm.whichdb(self.filename) == 'dbm.gnu':
            mode += 'u'

        self.shelf = shelve.open(self.filename, mode)

        self.check_control_data()

        if self.caching == CACHE_ALWAYS or\
                (self.caching == CACHE_ON_CONNS and self.has_conns):
            for key in self.shelf:
                self.cache[key] = self.shelf[key]

        self.index = list(self.shelf.keys())

        log.debug("Shelf opened: %s" % self.shelf)

    def __setitem__(self, name, value):
        self.cache[name] = value
        self.update_mod()

    def __getitem__(self, name):
        if name in self.cache:
            return self.cache[name]
        return self.shelf[name]

    def __contains__(self, name):
        if name in self.cache:
            return True
        if name in self.index:
            return True
        return False

    def __delitem__(self, name):
        if name in self.cache:
            del self.cache[name]

        if name in self.index:
            self.index.remove(name)
            del self.shelf[name]

        self.update_mod()

    def update_umod(self):
        if "control" not in self.cache:
            self.cache["control"] = self.shelf['control']

        ts = int(time.mktime(time.gmtime()))
        self.cache["control"]["canto-user-modified"] = ts
        self.cache["control"]["canto-modified"] = ts

    def update_mod(self):
        if "control" not in self.cache:
            self.cache["control"] = self.shelf['control']

        ts = int(time.mktime(time.gmtime()))
        self.cache["control"]["canto-modified"] = ts

    @wlock_feeds
    def sync(self):

        # Check here in case we're called after close by plugins that
        # don't know better.
        if self.shelf == None:
            log.debug("No shelf.")
            return

        for key in self.cache:
            self.shelf[key] = self.cache[key]

        if self.caching == CACHE_OFF or\
                (self.caching == CACHE_ON_CONNS and not self.has_conns):
            self.cache = {}
            log.debug("Unloaded.")

        self.shelf.sync()
        log.debug("Synced.")

        if dbm.whichdb(self.filename) == 'dbm.gnu':
            self.shelf.close()
            self._reorganize()
            self.open()

    def _reorganize(self):
        # This is a workaround for shelves implemented with database types
        # (like gdbm) that won't shrink themselves.

        # Because we're a delete heavy workload (as we drop items that are no
        # longer relevant), we check for reorganize() and use it on close,
        # which should shrink the DB and keep it from growing into perpetuity.

        try:
            db = dbm.open(self.filename, "wu")
            getattr(db, 'reorganize')()
            db.close()
        except Exception as e:
            log.warn("Failed to reorganize db:")
            log.warn(traceback.format_exc())
        else:
            log.debug("Successfully trimmed db")

    def close(self):
        log.debug("Closing.")
        self.sync()
        self.shelf.close()
        self.shelf = None
        call_hook("daemon_db_close", [self.filename])
