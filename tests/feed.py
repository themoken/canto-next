#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.feed import CantoFeed
import unittest

class StubShelf(dict):
    def open(self, *args):
        pass

    def close(self, *args):
        pass

TEST_URL = "http://example.com/rss"

class Tests(unittest.TestCase):
    def test_first_update(self):
        shelf = StubShelf()
        feed = CantoFeed(shelf, "Example", TEST_URL, 5, 100)

        feed.update_contents = \
                { "entries" : [ { "id" : "1" },\
                                { "id" : "2" }]}

        feed.index()

        # index() clears update contents
        self.assertTrue(feed.update_contents == None)
        self.assertTrue(feed.items ==\
                [ { "id" : (TEST_URL, "1") },
                  { "id" : (TEST_URL, "2") } ])

    def test_attribute_passthru(self):
        shelf = StubShelf()
        shelf[TEST_URL] = { "entries" : [ {"id" : "1", "canto_test" : "abc",
                                            "canto_update" : "samesame"} ] }

        feed = CantoFeed(shelf, "Example", TEST_URL, 5, 100)

        feed.update_contents = \
                { "entries" : [ { "id" : "1", "canto_update" : "different" } ] }

        feed.index()

        self.assertTrue(feed.update_contents == None)
        self.assertTrue(feed.items == [ { "id" : (TEST_URL, "1") }])

        # Make sure canto_update was moved over, but allowed to be different.

        self.assertTrue("canto_update" in shelf[TEST_URL]["entries"][0])
        self.assertTrue(shelf[TEST_URL]["entries"][0]["canto_update"] == "different")

        # Make sure other canto_* items are moved over, even if not in the
        # original.

        self.assertTrue("canto_test" in shelf[TEST_URL]["entries"][0])
        self.assertTrue(shelf[TEST_URL]["entries"][0]["canto_test"] == "abc")
