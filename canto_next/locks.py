# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .rwlock import RWLock

# NOTE: feed_lock and tag_lock only protect the existence of Feed() and Tag()
# objects, and their configuration. The Tag() objects have their own locks the
# protect their content.

feed_lock = RWLock('feed_lock')
tag_lock = RWLock('tag_lock')

# NOTE: if config_lock is held writable, feed_lock and tag_lock must also be
# held writable.

config_lock = RWLock('config_lock')

# The rest of these are independent.
watch_lock = RWLock('watch_lock')
attr_lock = RWLock('attr_lock')
socktran_lock = RWLock('socktran_lock')
hook_lock = RWLock('hook_look')
