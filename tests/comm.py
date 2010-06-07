# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.client import CantoClient
from canto.server import CantoServer
from Queue import Queue
import unittest
import time
import sys
import os

SOCKET_NAME=".canto_socket"

class Tests(unittest.TestCase):
    def test_communication(self):
        server_pid = os.fork()
        if not server_pid:
            self.test_server()
            os._exit(0)
        print "Forked: %d" % server_pid

        client_pid = os.fork()
        if not client_pid:
            self.test_client()
            os._exit(0)
        print "Forked: %d" % client_pid

    def test_server(self):
        self.queue = Queue()
        self.server = CantoServer(SOCKET_NAME, self.queue, True)
        self.server.get_one_cmd()

        self.assertTrue(not self.queue.empty())
        cmd = self.queue.get()

        self.assertTrue(cmd[1][0] == "BASIC")
        self.assertTrue(cmd[1][1] == "TEST")

    def test_client(self):
        while not os.path.exists(SOCKET_NAME): pass
        self.client = CantoClient(SOCKET_NAME)
        self.client.write("BASIC", "TEST")
        while not self.client.hupped:
            self.client.read()
