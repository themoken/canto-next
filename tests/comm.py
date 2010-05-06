# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.client import CantoClient
from canto.server import CantoServer
from Queue import Queue
import unittest
import sys
import os

SOCKET_NAME=".canto_socket"

class Tests(unittest.TestCase):
    def test_communication(self):
        client_pid = os.fork()
        if not client_pid:
            self.test_server()
            return

        server_pid = os.fork()
        if not server_pid:
            self.test_client()
            return

        os.waitpid(client_pid, 0)
        os.waitpid(server_pid, 0)

    def test_server(self):
        self.queue = Queue()
        self.server = CantoServer(SOCKET_NAME, self.queue, True)
        self.server.get_one_cmd()
        cmd = self.queue.get()
        print cmd

    def test_client(self):
        while not os.path.exists(SOCKET_NAME): pass
        self.client = CantoClient(SOCKET_NAME)
        self.client.write("BASIC", "TEST")
