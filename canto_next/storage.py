# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .hooks import on_hook

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
    def __init__(self, filename, writeback):
        self.writeback = writeback
        self.filename = filename
        self.lock = threading.Lock()

        self._open()

        # Sync after a block of requests has been fulfilled,
        # close the database all together on exit.

        on_hook("work_done", self.sync)
        on_hook("exit", self.close)

    def _need_lock(fn):
        def lockfn(self, *args, **kwargs):
            self.lock.acquire()
            r = fn(self, *args, **kwargs)
            self.lock.release()
            return r
        return lockfn

    # Lock held above this function, unnecessary in init.
    def _open(self):
        if self.writeback:
            self.shelf = shelve.open(self.filename, 'c', None, True)
        else:
            self.shelf = shelve.open(self.filename)

    @_need_lock
    def __setitem__(self, name, value):
        self.shelf[name] = value

    @_need_lock
    def __getitem__(self, name):
        r = self.shelf[name]
        return r

    @_need_lock
    def __contains__(self, name):
        return name in self.shelf

    @_need_lock
    def __delitem__(self, name):
        del self.shelf[name]

    @_need_lock
    def sync(self):
        self.shelf.sync()

    @_need_lock
    def trim(self):
        self._close()
        tries = 3
        while tries > 0:
            try:
                self._open()
            except Exception as e:
                log.warn("Failed to reopen db after trim:")
                log.warn(traceback.format_exc())
            tries -= 1
            time.sleep(0.5)

    # Lock held in close()
    def _reorganize(self):
        # This is a workaround for shelves implemented with database types
        # (like gdbm) that won't shrink themselves.

        # Because we're a delete heavy workload (as we drop items that are no
        # longer relevant), we check for reorganize() and use it on close,
        # which should shrink the DB and keep it from growing into perpetuity.

        log.debug("Checking for DB trim")

        try:
            need_reorg = False
            db = dbm.open(self.filename, "r")
            if hasattr(db, 'reorganize'):
                need_reorg = True
            db.close()

            if need_reorg:
                # Workaround Python bug 13947 (gdbm reorganize leaving hanging
                # file descriptors) by opening the extra fds in a temporary
                # process.

                pid = os.fork()
                if not pid:

                    # Wrap everything to make sure we don't get back into the
                    # primary server code.

                    try:
                        db = dbm.open(self.filename, "w")
                        getattr(db, 'reorganize')()
                        log.debug("Reorged - dying\n")
                        db.close()
                    except:
                        pass
                    sys.exit(0)

                log.debug("Reorg forked as %d" % pid)
                tries = 3
                while True:
                    try:
                        tries -= 1
                        os.waitpid(pid, 0)
                        break
                    except Exception as e:
                        log.debug("Waiting, got: %s" % e)
                        if tries <= 0:
                            log.debug("Abandoning %d" % pid)
                            break

        except Exception as e:
            log.warn("Failed to reorganize db:")
            log.warn(traceback.format_exc())

    def _close(self):
        self.shelf.close()
        self._reorganize()
        self.shelf = None

    @_need_lock
    def close(self):
        self._close()
