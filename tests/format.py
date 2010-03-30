#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.format import get_formatter
import unittest

class Tests(unittest.TestCase):
    def setUp(self):
        self.keys = { 'a' : "alpha", 'b' : "beta" }
        self.subs = { "alpha" : "Lorem", "beta" : "ipsum" }

    def one_test(self, fmt, expected, extrakeys = {}):
        newkeys = self.keys.copy()
        newkeys.update(extrakeys)
        f = get_formatter(fmt, newkeys)
        result = f(self.subs)

        self.assert_(result == expected)

    def test_basic_substitution(self):
        self.one_test("%a - %b", "Lorem - ipsum")

    def test_escape(self):
        self.one_test("%a\%%b", "Lorem%ipsum")

    def test_unmapped_escape(self):
        self.one_test("%a %b %c", "Lorem ipsum ")

    def test_missing_mapping(self):
        self.one_test("%a %b %c", "Lorem ipsum ", { "c" : "test3" })
