#! -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto import config, storage, fetch
import threading
import unittest
import time
import os

FEED_SHELF = "feed.shelf"

class Tests(unittest.TestCase):

    def fresh_fetch(self, config_path):
        if os.path.exists(FEED_SHELF):
            os.unlink(FEED_SHELF)

        self.shelf = storage.CantoShelf(FEED_SHELF)

        self.cfg = config.CantoConfig(config_path, self.shelf)
        self.cfg.parse()

        self.fetch = fetch.CantoFetch(self.shelf, self.cfg.feeds)
        self.fetch.fetch()
        self.fetch.process()

    def test_good_fetch(self):
        self.fresh_fetch("tests/good/fetch-test.conf")

        # Make sure only the main "thread" is running.
        self.assert_(not threading.activeCount() > 1)

        # Make sure we got non-None parsed output.
        self.shelf.open()
        for feed in self.cfg.feeds:
            self.assert_(feed.URL in self.shelf)
        self.shelf.close()

    def test_bad_fetch(self):
        self.fresh_fetch("tests/bad/fetch-test.conf")

        # Make sure only the main "thread" is running.
        self.assert_(threading.activeCount() == 1)

        # Make sure the bad feed didn't get parsed somehow
        self.shelf.open()
        for feed in self.cfg.feeds:
            self.assert_(feed.URL not in self.shelf)
        self.shelf.close()

    def test_rate(self):
        self.fresh_fetch("tests/good/fetch-test.conf")

        self.shelf.open()

        # This feed shouldn't get updated.
        unupdated_time = time.time() - (self.cfg.feeds[0].rate - 1) * 60

        f = self.shelf[self.cfg.feeds[0].URL]
        f["canto_update"] = unupdated_time
        self.shelf[self.cfg.feeds[0].URL] = f

        # This feed should get updates.
        updated_time = time.time() - (self.cfg.feeds[1].rate + 1) * 60

        f = self.shelf[self.cfg.feeds[1].URL]
        f["canto_update"] = updated_time
        self.shelf[self.cfg.feeds[1].URL] = f

        myfetch = fetch.CantoFetch(self.shelf, self.cfg.feeds)
        myfetch.fetch()
        myfetch.process()

        # Make sure the expired feed has been updated and that
        # the more recent feed has not.

        self.assert_(self.shelf[self.cfg.feeds[0].URL]["canto_update"] ==\
                unupdated_time)
        self.assert_(self.shelf[self.cfg.feeds[1].URL]["canto_update"] !=\
                updated_time)
        self.shelf.close()

    def tearDown(self):
        # Cleanup test shelf.
        os.unlink(FEED_SHELF)
