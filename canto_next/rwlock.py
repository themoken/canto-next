# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

# Seriously python? No RWlock?

from threading import Lock, current_thread
import traceback
import time

alllocks = []

class RWLock(object):
    def __init__(self, name=""):
        self.name = name
        self.readers = 0
        self.lock = Lock()

        self.writer_stack = []
        self.writer_id = ""

        alllocks.append(self)

    def acquire_read(self):
        self.lock.acquire()
        self.readers += 1
        self.lock.release()

    def release_read(self):
        self.readers -= 1

    def acquire_write(self):
        self.lock.acquire()

        self.writer_stack = traceback.format_stack()
        self.writer_id = current_thread();

        while (self.readers > 0):
            time.sleep(0.1)

    def release_write(self):
        self.writer_stack = []
        self.writer_id = 0
        self.lock.release()
