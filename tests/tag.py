#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.tag import alltags, CantoTag
import unittest

class Tests(unittest.TestCase):

    def setUp(self):
        self.id1 = ("someURL", "someID")
        self.id2 = ("someURL", "someID2")
        self.id1_again = ("someURL", "someID")

    def test_add_tag(self):
        self.assertTrue(alltags.tags == {})

        alltags.add_tag(self.id1, "tag1")

        # Ensure the id has been added to tag.
        self.assertTrue(len(alltags.tags.keys()) == 1)
        self.assertTrue("tag1" in alltags.tags)
        self.assertTrue(self.id1 in alltags.tags["tag1"])
        self.assertTrue(len(alltags.tags["tag1"]) == 1)

        # Make sure we're getting set() behavior.
        alltags.add_tag(self.id1_again, "tag1")
        self.assertTrue(len(alltags.tags["tag1"]) == 1)

        # Test adding to already existing tag.
        alltags.add_tag(self.id2, "tag1")
        self.assertTrue(len(alltags.tags.keys()) == 1)
        self.assertTrue(self.id2 in alltags.tags["tag1"])
        self.assertTrue(self.id1 in alltags.tags["tag1"])

        # Adding more than one new tag.
        alltags.add_tag(self.id2, "tag2")
        self.assertTrue(len(alltags.tags.keys()) == 2)
        self.assertTrue(self.id2 in alltags.tags["tag2"])
        self.assertTrue(self.id1 not in alltags.tags["tag2"])

    def test_remove_id(self):
        alltags.remove_id(self.id1)
        for tag in alltags.tags:
            self.assertTrue(self.id1 not in alltags.tags[tag])
