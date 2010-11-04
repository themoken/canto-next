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

    def open(self, *args):
        if not self.refs:
            self.shelf = shelve.open(self.filename, *args)
        self.refs += 1

    def close(self):
        if self.refs == 1:
            self.shelf.close()
            self.shelf = None
        else:
            self.shelf.sync()
        self.refs -= 1
