#! -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.feed import CantoFeed
from canto.tag import alltags

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

    def test_id_hierarchy(self):
        shelf = StubShelf()
        feed = CantoFeed(shelf, "Example", TEST_URL, 5, 100)

        # Item has no ID property, but has link and title.
        feed.update_contents = \
                { "entries" :
                  # First entry has title and link, no ID
                [ { "link" : "testlink",
                    "title" : "Item 1",
                    "canto_update" : "different" },
                  # Second entry has title, no link or ID
                  { "title" : "Item 2",
                    "canto_update" : "different" },
                  # Third is a crap entry, with nothing
                  { "other_att" : "crap",
                    "canto_update" : "crapcrap" }
                ]
                }

        feed.index()

        self.assertTrue(feed.update_contents == None)
        self.assertTrue(len(feed.items) == 2)
        self.assertTrue(feed.items[0] == { "id" : (TEST_URL, "testlink") })
        self.assertTrue(feed.items[1] == { "id" : (TEST_URL, "Item 2") })

    def test_unique_id(self):
        shelf = StubShelf()
        feed = CantoFeed(shelf, "Example", TEST_URL, 5, 100)

        # Empty items.
        self.assertTrue(feed.unique_item({"id" : "anyid" }) == True)

        feed.update_contents = { "entries" : [ { "id" : "anyid" },
                                               { "id" : "anyid" }
                                             ]
                               }
        feed.index()

        self.assertTrue(feed.unique_item({"id" : "anyid" }) == False)
        self.assertTrue(len(feed.items) == 1)
        self.assertTrue(feed.items[0] == { "id" : (TEST_URL, "anyid") } )

    def test_clear_tags(self):
        alltags.reset()

        shelf = StubShelf()
        feed = CantoFeed(shelf, "Example", TEST_URL, 5, 100)

        id1 = (TEST_URL, "item1")
        id2 = (TEST_URL, "item2")

        alltags.add_tag(id1, "Example")
        alltags.add_tag(id2, "Example")
        alltags.add_tag(id1, "othertag1")
        alltags.add_tag(id2, "othertag2")

        self.assertTrue(id1 in alltags.tags["Example"])
        self.assertTrue(id2 in alltags.tags["Example"])
        self.assertTrue(id1 in alltags.tags["othertag1"])
        self.assertTrue(id2 in alltags.tags["othertag2"])

        feed.olditems = [ { "id" : (TEST_URL, "item1") },
                          { "id" : (TEST_URL, "item2") }]
        feed.items = [ { "id" : (TEST_URL, "item2") } ]

        feed.clear_tags()

        self.assertTrue(id1 not in alltags.tags["Example"])
        self.assertTrue(id1 not in alltags.tags["othertag1"])
        self.assertTrue(id2 in alltags.tags["Example"])
        self.assertTrue(id2 in alltags.tags["othertag2"])
