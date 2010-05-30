#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.encoding import *
import unittest
import locale

class Tests(unittest.TestCase):

    def setUp(self):
        self.enc = locale.getpreferredencoding()
        self.unicode_string = u"" # A couple of penguins for you.
        self.encoded_string = "abcdef"

    def _test_encoder(self, encodr):
        self.assertEqual(type(encodr(self.unicode_string)), str)

    def _test_decoder(self, decodr):
        res = decodr(self.encoded_string)
        self.assertEqual(type(res), unicode)
        self.assertEqual(res, self.encoded_string)

    def test_defaults(self):
        self._test_encoder(encoder)
        self._test_decoder(decoder)

    def test_set_encoding(self):
        test_encoding = "iso-8859-1"
        if self.enc == test_encoding:
            test_encoding = "iso-8859-15"

        e = get_encoder("replace", "iso-8859-1")
        d = get_decoder("replace", "iso-8859-1")

        self._test_encoder(e)
        self._test_decoder(d)


if __name__ == "__main__":
    unittest.main()
