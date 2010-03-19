#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto import config, storage, canto_fetch
import threading
import logging

log = logging.getLogger("CF-TEST")

FEED_SHELF = "feed.shelf"

def test_good_fetch_test():
    shelf = storage.CantoShelf(FEED_SHELF)

    cfg = config.CantoConfig("tests/good/fetch-test.conf", shelf)
    cfg.parse()

    fetch = canto_fetch.CantoFetch(shelf, cfg.feeds)
    fetch.fetch()

    # Make sure only the main "thread" is running.
    if threading.activeCount() > 1:
        log.debug("fetch returned, threads still active!")
        return 0

    # Make sure we got non-None parsed output.
    feed = cfg.feeds[0]
    if not feed.feedparsed:
        log.debug("failed to get feedparser output!")
        return 0

    return 1

def test_bad_fetch_test():
    shelf = storage.CantoShelf(FEED_SHELF)

    cfg = config.CantoConfig("tests/bad/fetch-test.conf", shelf)
    cfg.parse()

    fetch = canto_fetch.CantoFetch(shelf, cfg.feeds)
    fetch.fetch()

    # Make sure only the main "thread" is running.
    if threading.activeCount() > 1:
        log.debug("fetch returned, threads still active!")
        return 0

    feed = cfg.feeds[0]
    if feed.feedparsed:
        log.debug("Got feedparser output for bad feed!?")
        return 0

    return 1

def test():
    if not test_good_fetch_test():
        log.debug("FAILED test_good_fetch_test")
        return
    if not test_bad_fetch_test():
        log.debug("FAILED test_bad_fetch_test")
        return

    print "CANTO-FETCH TESTS PASSED"

def cleanup():
    pass
