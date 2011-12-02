# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from hooks import on_hook

import traceback
import logging
import shelve
import anydbm

log = logging.getLogger("SHELF")

class CantoShelf():
    def __init__(self, filename, writeback):
        self.writeback = writeback
        self.filename = filename

        self._open()

        # Sync after a block of requests has been fulfilled,
        # close the database all together on exit.

        on_hook("work_done", self.sync)
        on_hook("exit", self.close)

    def _open(self):
        if self.writeback:
            self.shelf = shelve.open(self.filename, 'c', None, True)
        else:
            self.shelf = shelve.open(self.filename)

    def __setitem__(self, name, value):
        name = name.encode("UTF-8")
        self.shelf[name] = value

    def __getitem__(self, name):
        name = name.encode("UTF-8")
        r = self.shelf[name]
        return r

    def __contains__(self, name):
        name = name.encode("UTF-8")
        return name in self.shelf

    def __delitem__(self, name):
        name = name.encode("UTF-8")
        del self.shelf[name]

    def sync(self):
        self.shelf.sync()

    def trim(self):
        self.close()
        self._open()

    def _reorganize(self):
        # This is a workaround for shelves implemented with database types
        # (like gdbm) that won't shrink themselves.

        # Because we're a delete heavy workload (as we drop items that are no
        # longer relevant), we check for reorganize() and use it on close,
        # which should shrink the DB and keep it from growing into perpetuity.

        # Counter intuitively, this only requires read permissions and, in
        # fact there seems to be an issue lately with shelves getting EAGAIN
        # on open if this is a writer.

        try:
            db = anydbm.open(self.filename, "r")
            if hasattr(db, 'reorganize'):
                reorg = getattr(db, 'reorganize')
                reorg()
            db.close()
        except Exception, e:
            log.warn("Failed to reorganize db:")
            log.warn(traceback.format_exc())

    def close(self):
        self.shelf.close()
        self._reorganize()
        self.shelf = None
