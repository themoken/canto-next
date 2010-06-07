#! -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.protocol import CantoSocket
import unittest
import os

SOCKET_NAME=".canto_socket"

class Tests(unittest.TestCase):
    def setUp(self):
        try:
            os.unlink(SOCKET_NAME)
        except:
            pass

        self.assert_(not os.path.exists(SOCKET_NAME))
        self.cs = CantoSocket(SOCKET_NAME, server=True)        

    def test_socket_creation(self):
        self.assert_(os.path.exists(SOCKET_NAME))

    def test_parser(self):
        # NULL info returns None
        self.assert_(self.cs.parse("\0") == None)

        # Make sure message only splits once
        self.assert_(self.cs.parse("CMD \"MESSAGE STUFF\"\0") ==
                ("CMD", "MESSAGE STUFF"))

        # Make sure we only get full parsed messages
        self.assert_(self.cs.parse("CMD \"MESSAGE STUFF\"\0TRAILING \"...") ==
                ("CMD", "MESSAGE STUFF"))

        print self.cs.fragment

        # Make sure message fragments are kept and reassembled
        self.assert_(self.cs.parse("COMMAND SEQUENCE\"\0") ==
                ("TRAILING", "...COMMAND SEQUENCE"))

        # Make sure malformed fragments return None
        self.assert_(self.cs.parse("MALFORMED\0") == None)

        # And aren't remembered
        self.assert_(self.cs.parse("WELL \"FORMED\"\0") ==
                ("WELL", "FORMED"))

    def tearDown(self):
        os.unlink(SOCKET_NAME)
