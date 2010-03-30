#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto import config, storage
import unittest

FEED_SHELF="feed.shelf"

class Tests(unittest.TestCase):

    def fresh_parse(self, config_path):
        # Shelf should be unused...
        self.shelf = storage.CantoShelf(FEED_SHELF)
        self.cfg = config.CantoConfig(config_path, self.shelf)
        self.cfg.parse()

    def test_good_basic(self):
        self.fresh_parse("tests/good/basic.conf")
        feed = self.cfg.feeds[0]

        # Right URL
        self.assert_(feed.URL == "http://science.reddit.com/.rss")

        # Got rate from config
        self.assert_(feed.rate == self.cfg.rate)

        # *Didn't* get keep from config
        self.assert_(feed.keep != self.cfg.keep)
        self.assert_(feed.keep == 40)

        # No errors in good config
        self.assert_(not self.cfg.errors)

    def test_bad_basic(self):
        self.fresh_parse("tests/bad/basic.conf")

        # Make sure non of the invalid feeds made it through
        self.assert_(not self.cfg.feeds)

        # Make sure we fell back to default for malformed.
        self.assert_(type(self.cfg.rate) == int)

        # Make sure cfg.errors is set
        self.assert_(self.cfg.errors)
