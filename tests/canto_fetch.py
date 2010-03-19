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

def test():
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

    print "CANTO-FETCH TEST PASSED"
    return 1

def cleanup():
    pass
