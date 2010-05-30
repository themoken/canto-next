# -*- coding: utf-8 -*-
#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# This interface is developer only. It allows you to communicate to the server @
# ~/.canto-ng/.canto_socket using plaintext, hand written commands and
# asynchronously get responses. At a later time it might be made more full
# featured for development with things like reading scripts out of a file, but
# at the moment it's just there to test basic traffic over the socket.

from client import CantoClient
from threading import Thread
import os

class CantoInterface(CantoClient):
    def __init__(self):
        CantoClient.__init__(self, os.getenv("HOME") +
            "/.canto-ng/.canto_socket")
        self.response_alive = False

    # Read any input from the socket and print it.
    def response_thread(self):
        while self.response_alive:
            r = self.read(1)

            # HUP
            if r == 16:
                break
            if r:
                print r

    def run(self):
        # Start response printing thread
        thread = Thread(target=self.response_thread)
        self.response_alive = True
        thread.start()

        while not self.hupped:
            cmd = raw_input("")

            # The only special command at this point.
            if cmd == "exit":
                print "Exiting..."
                break

            parsed = cmd.split(" ", 1)
            if(len(parsed) < 2):
                print "Bad command"
                continue

            self.write(parsed[0], parsed[1])

        self.response_alive = False
        thread.join()
