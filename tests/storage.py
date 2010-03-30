#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto import storage
import unittest
import os

TEST_SHELF = "test.shelf"

class Tests(unittest.TestCase):

    def setUp(self):
        # Eliminate old test shelf
        if os.path.exists(TEST_SHELF):
            os.unlink(TEST_SHELF)

        # Grab new, empty test shelf
        self.shelf = storage.CantoShelf(TEST_SHELF)

    def test_basic_storage(self):
        # Test initial ref counting
        self.shelf.open()
        self.assert_(self.shelf.refs == 1)

        # Test second ref
        self.shelf.open()
        self.assert_(self.shelf.refs == 2)

        # Test  __contains__ fail
        self.assert_("test" not in self.shelf)

        # Test __setitem__
        self.shelf["test"] = "123"

        # Test ref counting close
        self.shelf.close()
        self.assert_(self.shelf.refs == 1)

        # Test __contains__ pass
        self.assert_("test" in self.shelf)

        # Test __getitem__
        self.assert_(self.shelf["test"] == "123")

        # Test __delitem__
        del self.shelf["test"]

        self.assert_("test" not in self.shelf)

        self.shelf.close()
        self.assert_(self.shelf.refs == 0)

    def tearDown(self):
        os.unlink(TEST_SHELF)
