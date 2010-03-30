# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging

log = logging.getLogger("FEED")

class CantoFeed():
    def __init__(self, shelf, URL, rate, keep):
        self.shelf = shelf
        self.URL = URL
        self.rate = rate
        self.keep = keep

        self.update_contents = None
