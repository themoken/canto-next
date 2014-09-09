# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
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

class CantoShelf():
    def __init__(self, filename):
        self.filename = filename

        self.cache = {}

        self.open()

    def open(self):
        call_hook("daemon_db_open", [self.filename])

        mode = 'c'
        if dbm.whichdb(self.filename) == 'dbm.gnu':
            mode += 'u'

        self.shelf = shelve.open(self.filename, mode)
        log.debug("Shelf opened: %s" % self.shelf)

    def __setitem__(self, name, value):
        self.cache[name] = value

    def __getitem__(self, name):
        if name in self.cache:
            return self.cache[name]
        return self.shelf[name]

    def __contains__(self, name):
        if name in self.cache:
            return True
        return name in self.shelf

    def __delitem__(self, name):
        if name in self.cache:
            del self.cache[name]
            try:
                del self.shelf[name]
            except:
                pass
        del self.shelf[name]

    def update_umod(self):
        if "control" not in self.cache:
            self.cache["control"] = {}
        self.cache["control"]["canto-user-modified"] = int(time.time())

    @wlock_feeds
    def sync(self):

        # Check here in case we're called after close by plugins that
        # don't know better.
        if self.shelf == None:
            log.debug("No shelf.")
            return

        for key in self.cache:
            self.shelf[key] = self.cache[key]
        self.cache = {}

        self.shelf.sync()
        log.debug("Synced.")

        if dbm.whichdb(self.filename) == 'dbm.gnu':
            self.shelf.close()
            self._reorganize()
            self.open()
            log.debug("Trimmed.")

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
