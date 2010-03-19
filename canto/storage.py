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

# Decorator to make self.shelf appear always instantiated
def open_close(fn):
    def open_close_dec(self, *args):
        self.shelf = shelve.open(self.filename)
        log.debug("Opened Shelf %s" % self.filename)

        ret = fn(self, *args)

        self.shelf.close()
        log.debug("Closed Shelf %s" % self.filename)
        self.shelf = None
        return ret

    return open_close_dec

class CantoShelf():
    def __init__(self, filename):
        self.filename = filename

    # == Dict wrappers ==

    @open_close
    def __setitem__(self, name, value):
        log.debug("Set shelf[%s] = %s" % (name, value))
        self.shelf[name] = value

    @open_close
    def __getitem__(self, name):
        r = self.shelf[name]
        log.debug("Got shelf[%s] -> %s" % (name, r))
        return r

    @open_close
    def __contains__(self, name):
        r = name in self.shelf
        if r:
            log.debug("shelf contains %s" % name)
        else:
            log.debug("shelf doesn't contain %s" % name)
        return r

    @open_close
    def __delitem__(self, name):
        del self.shelf[name]
        log.debug("deleted %s from shelf" % name)
