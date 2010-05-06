# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from protocol import CantoSocket

import logging
import select

log = logging.getLogger("CLIENT")

class CantoClient(CantoSocket):
    def __init__(self, socket_name):
        CantoSocket.__init__(self, socket_name, server=False)
        self.conn = self.socket
        self.hupped = 0

    # Write a (cmd, args)
    def write(self, cmd, args):
        self.do_write(self.conn, cmd, args)

    # Read a (cmd, args)
    def read(self):
        r = self.do_read(self.conn)
        if r == select.POLLHUP:
            self.hupped = 1
        return r
