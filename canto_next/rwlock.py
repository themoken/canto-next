# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# Seriously python? No RWlock?

from threading import RLock, current_thread
import traceback
import time

import logging
log = logging.getLogger("RWLOCK")

alllocks = []

class RWLock(object):
    def __init__(self, name=""):
        self.name = name
        self.readers = 0
        self.reader_stacks = []
        self.lock = RLock()
        self.reader_lock = RLock()

        self.writer_stacks = []
        self.writer_id = 0

        alllocks.append(self)

    def acquire_read(self, block=True):

        # Hold reader_lock to see if we've already actually got this lock.

        r = self.reader_lock.acquire(block)
        if not r:
            return r

        cti = current_thread().ident
        if cti == self.writer_id or cti in [ x[0] for x in self.reader_stacks ]:
            self.readers += 1
            self.reader_stacks.append((current_thread().ident, traceback.format_stack()))
            self.reader_lock.release()
            return True

        # Release the lock so that if we block on getting the main lock, other
        # threads can still perform the above check and release_read().

        self.reader_lock.release()

        # Get full lock so writers can keep us from getting a lock we don't
        # already hold.

        r = self.lock.acquire(block)
        if not r:
            return r

        # Re-acquire reader_lock so we can manipulate the vars.

        self.reader_lock.acquire()

        self.readers += 1
        self.reader_stacks.append((current_thread().ident, traceback.format_stack()))

        # Release everything.

        self.reader_lock.release()
        self.lock.release()
        return True

    def release_read(self):
        last = False

        self.reader_lock.acquire()
        self.readers -= 1

        for tup in reversed(self.reader_stacks[:]):
            if tup[0] == current_thread().ident:
                self.reader_stacks.remove(tup)
                break

        if self.readers == 0:
            last = True

        self.reader_lock.release()
        return last

    def acquire_write(self, block=True):
        r = self.lock.acquire(block)

        if not r:
            return r

        self.writer_stacks.append(traceback.format_stack())
        self.writer_id = current_thread().ident;

        warned = False

        while self.readers > 0:
            if current_thread().ident in [ x[0] for x in self.reader_stacks ]:
                if not warned:
                    log.debug("WARN: %s holds read, trying to get write on %s", 
                            current_thread().ident, self.name)
                    warned = True

                # Break the deadlock if we're the last reader
                if len(self.reader_stacks) == 1:
                    break

            time.sleep(0.1)
        return True

    def release_write(self):
        last = False

        self.writer_stacks = self.writer_stacks[0:-1]
        if self.writer_stacks == []:
            self.writer_id = 0
            last = True

        self.lock.release()

        return last

def read_lock(lock):
    def _rlock_fn(fn):
        def _rlock(*args, **kwargs):
            lock.acquire_read()
            try:
                return fn(*args, **kwargs)
            finally:
                lock.release_read()
        return _rlock
    return _rlock_fn

def write_lock(lock):
    def _wlock_fn(fn):
        def _wlock(*args, **kwargs):
            lock.acquire_write()
            try:
                return fn(*args, **kwargs)
            finally:
               lock.release_write()
        return _wlock
    return _wlock_fn
