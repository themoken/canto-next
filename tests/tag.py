#! -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.tag import alltags
import unittest

class Tests(unittest.TestCase):

    def setUp(self):
        self.id1 = ("someURL", "someID")
        self.id2 = ("someURL", "someID2")
        self.id1_again = ("someURL", "someID")

    def test_add_tag(self):
        alltags.reset()

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

    # Basic setup for following (non-add_tag) tests.
    def basic_setup(self):
        alltags.reset()

        alltags.add_tag(self.id1, "tag1")
        alltags.add_tag(self.id1_again, "tag1")
        alltags.add_tag(self.id2, "tag1")
        alltags.add_tag(self.id2, "tag1")
        alltags.add_tag(self.id2, "tag2")

    def test_get_tag(self):
        self.basic_setup()

        tag1 = alltags.get_tag("tag1")
        tag2 = alltags.get_tag("tag2")
        tag3 = alltags.get_tag("tag3")

        self.assertTrue(tag1 ==\
                set([("someURL", "someID"),("someURL", "someID2")]))
        self.assertTrue(tag2 ==\
                set([("someURL", "someID2")]))
        self.assertTrue(tag3 == [])

    def test_remove_id(self):
        self.basic_setup()

        alltags.remove_id(self.id1)
        for tag in alltags.tags:
            self.assertTrue(self.id1 not in alltags.tags[tag])
