# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# Seriously python? No RWlock?

from threading import Lock, current_thread
import traceback
import time

alllocks = []

class RWLock(object):
    def __init__(self, name=""):
        self.name = name
        self.readers = 0
        self.reader_stacks = []
        self.lock = Lock()

        self.writer_stack = []
        self.writer_id = 0

        alllocks.append(self)

    def acquire_read(self):
        self.lock.acquire()
        self.readers += 1
        self.reader_stacks.append((current_thread(), traceback.format_stack()))
        self.lock.release()

    def release_read(self):
        self.readers -= 1
        self.reader_stacks = [ x for x in self.reader_stacks if x[0] != current_thread() ]

    def acquire_write(self):
        self.lock.acquire()

        self.writer_stack = traceback.format_stack()
        self.writer_id = current_thread().ident;

        while (self.readers > 0):
            time.sleep(0.1)

    def release_write(self):
        self.writer_stack = []
        self.writer_id = 0
        self.lock.release()

def read_lock(lock):
    def _rlock_fn(fn):
        def _rlock(*args, **kwargs):
            lock.acquire_read()
            r = fn(*args, **kwargs)
            lock.release_read()
            return r
        return _rlock
    return _rlock_fn

def write_lock(lock):
    def _wlock_fn(fn):
        def _wlock(*args, **kwargs):
            lock.acquire_write()
            r = fn(*args, **kwargs)
            lock.release_write()
            return r
        return _wlock
    return _wlock_fn

def assert_wlocked(lock):
    def _alock_fn(fn):
        def _alock(*args, **kwargs):
            if lock.writer_id != current_thread().ident:
                raise Exception("BUG: Function %s caller must hold lock %s (write)" % (fn, lock))
            return fn(*args, **kwargs)
        return _alock
    return _alock_fn

def assert_rlocked(lock):
    def _alock_fn(fn):
        def _alock(*args, **kwargs):
            if lock.readers <= 0 and lock.writer_id != current_thread().ident:
                raise Exception("BUG: Function %s caller must hold lock %s (read)" % (fn, lock))
            return fn(*args, **kwargs)
        return _alock
    return _alock_fn
