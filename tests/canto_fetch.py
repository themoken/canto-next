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
import time

log = logging.getLogger("CF-TEST")

FEED_SHELF = "feed.shelf"

def test_rate():
    shelf = storage.CantoShelf(FEED_SHELF)

    cfg = config.CantoConfig("tests/good/fetch-test.conf", shelf)
    cfg.parse()

    shelf.open()

    # This feed shouldn't get updated.
    f = shelf[cfg.feeds[0].URL]
    f["canto_update"] = time.time() - (cfg.feeds[0].rate - 1) * 60
    shelf[cfg.feeds[0].URL] = f

    # This feed should get updates.
    f = shelf[cfg.feeds[1].URL]
    f["canto_update"] = time.time() - (cfg.feeds[1].rate + 1) * 60
    shelf[cfg.feeds[1].URL] = f

    shelf.close()

    fetch = canto_fetch.CantoFetch(shelf, cfg.feeds)
    fetch.fetch()

    # Make sure we're done with them all.
    for thread, feed in fetch.threads:
        thread.join()

    if hasattr(cfg.feeds[0], "feedparsed"):
        log.debug("Feed updated too quickly!")
        return 0

    if not hasattr(cfg.feeds[1], "feedparsed"):
        log.debug("Feed not updated fast enough!")
        return 0

    return 1

def test_good_fetch_test():
    shelf = storage.CantoShelf(FEED_SHELF)

    cfg = config.CantoConfig("tests/good/fetch-test.conf", shelf)
    cfg.parse()

    fetch = canto_fetch.CantoFetch(shelf, cfg.feeds)
    fetch.fetch()
    fetch.process()

    # Make sure only the main "thread" is running.
    if threading.activeCount() > 1:
        log.debug("fetch returned, threads still active!")
        return 0

    # Make sure we got non-None parsed output.
    for feed in cfg.feeds:
        # Skip not-updated feeds
        if not hasattr(feed, "feedparsed"):
            continue

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
    fetch.process()

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
    if not test_rate():
        log.debug("FAILED test_rate")
        return

    print "CANTO-FETCH TESTS PASSED"

def cleanup():
    pass
