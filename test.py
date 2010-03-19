#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from tests import *
import logging

def run_tests():
    logging.basicConfig(
        filemode = "w",
        format = "%(asctime)s : %(name)s -> %(message)s",
        datefmt = "%H:%M:%S",
        level = logging.DEBUG
    )

    storage.test()
    config.test()
    canto_fetch.test()

def cleanup():
    storage.cleanup()
    config.cleanup()
    canto_fetch.cleanup()

if __name__ == "__main__":
    run_tests()
    cleanup()
