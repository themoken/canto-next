#!/usr/bin/python
# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from server import CantoServer

import Queue
import sys

SOCKET_NAME=".canto_socket"

class CantoBackend(CantoServer):
    def __init__(self):
        CantoServer.__init__(self, SOCKET_NAME, Queue.Queue())

    def pong(self, socket, args):
        self.write(socket, "PONG", "")

    def run(self):
        while 1:
            if not self.queue.empty():
                (socket, (cmd, args)) = self.queue.get()
                if cmd == "PING":
                    self.pong(socket, args)
            self.check_conns()

if __name__ == "__main__":
    back = CantoBackend()
    try:
        back.run()
    except KeyboardInterrupt:
        back.exit()
        sys.exit(0)
