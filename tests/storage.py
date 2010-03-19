#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto import storage
import logging
import os

log = logging.getLogger("TEST-SHELF")

TEST_SHELF = "test.shelf"
def test():
    # Eliminate old test shelf
    if os.path.exists(TEST_SHELF):
        os.unlink(TEST_SHELF)

    # Grab new, empty test shelf
    shelf = storage.CantoShelf(TEST_SHELF)

    # Test  __contains__ fail
    if "test" in shelf:
        log.debug("key in empty shelf!?")
        return 0

    # Test __setitem__
    shelf["test"] = "123"

    # Test __getitem__
    if shelf["test"] != "123":
        log.debug("value differs from just inserted value!")
        return 0

    if "test" not in shelf:
        log.debug("just inserted key not in shelf!?")
        return 0

    # Test __delitem__
    del shelf["test"]

    if "test" in shelf:
        log.debug("just deleted key still in shelf!?")
        return 0

    print "SHELF TEST PASSED"
    return 1
