# -*- coding: utf-8 -*-
#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from client import CantoClient
from threading import Thread
import os

class CantoInterface(CantoClient):
    def __init__(self):
        CantoClient.__init__(self, os.getenv("HOME") +
            "/.canto-ng/.canto_socket")
        self.response_alive = False

    def response_thread(self):
        while self.response_alive:
            r = self.read(1)
            if r == 16:
                break
            if r:
                print r

    def run(self):
        thread = Thread(target=self.response_thread)
        self.response_alive = True
        thread.start()

        while not self.hupped:
            cmd = raw_input("")

            # Special command, wait for response...
            if cmd == "wait":
                r = self.read()
                if r:
                    print r
                continue
            elif cmd == "exit":
                print "Exiting..."
                break

            parsed = cmd.split(" ", 1)
            if(len(parsed) < 2):
                print "Bad command"
                continue

            self.write(parsed[0], parsed[1])

        self.response_alive = False
        thread.join()
