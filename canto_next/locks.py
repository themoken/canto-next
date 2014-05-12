# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .rwlock import RWLock

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

# NOTE: feed_lock and tag_lock only protect the existence of Feed() and Tag()
# objects, and their configuration. The Tag() objects have their own locks the
# protect their content.

feed_lock = RWLock('feed_lock')
tag_lock = RWLock('tag_lock')

# NOTE: if config_lock is held writable, feed_lock and tag_lock must also be
# held writable.

config_lock = RWLock('config_lock')

# The rest of these are independent.
protect_lock = RWLock('protect_lock')
watch_lock = RWLock('watch_lock')
attr_lock = RWLock('attr_lock')
socktran_lock = RWLock('socktran_lock')
hook_lock = RWLock('hook_look')
fetch_lock = RWLock('fetch_lock')
