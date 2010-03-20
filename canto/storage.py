# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
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

    def __setitem__(self, name, value):
        log.debug("Set shelf[%s] = %s" % (name, value))
        self.shelf[name] = value

    def __getitem__(self, name):
        r = self.shelf[name]
        log.debug("Got shelf[%s] -> %s" % (name, r))
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
        log.debug("opened shelf")
        self.shelf = shelve.open(self.filename, *args)

    def close(self):
        log.debug("closed shelf")
        self.shelf.close()
        self.shelf = None
