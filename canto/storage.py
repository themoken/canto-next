# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging
import shelve

log = logging.getLogger("SHELF")

class CantoShelf():
    def __init__(self, filename):
        self.filename = filename
        self.refs = 0

    def __setitem__(self, name, value):
        log.debug("Set shelf[%s] = %s" % (name, value))
        self.shelf[name] = value

    def __getitem__(self, name):
        r = self.shelf[name]
        log.debug("Got shelf[%s]" % name)
        return r

    def __contains__(self, name):
        r = name in self.shelf
        if r:
            log.debug("shelf contains %s" % name)
        else:
            log.debug("shelf doesn't contain %s" % name)
        return r

    def __delitem__(self, name):
        del self.shelf[name]
        log.debug("deleted %s from shelf" % name)

    def open(self, *args):
        if not self.refs:
            log.debug("opened shelf")
            self.shelf = shelve.open(self.filename, *args)
        else:
            log.debug("incrementing shelf refs")
        self.refs += 1

    def close(self):
        if self.refs == 1:
            log.debug("closed shelf")
            self.shelf.close()
            self.shelf = None
        else:
            log.debug("decrementing shelf refs / sync")
            self.shelf.sync()
        self.refs -= 1
