#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto import config
import logging

log = logging.getLogger("TEST-SHELF")

FEED_SHELF="feed.shelf"

def test_good_basic():
    # Test basic config
    cfg = config.CantoConfig("tests/good/basic.conf", FEED_SHELF)
    cfg.parse()

    feed = cfg.feeds[0]

    # Correct URL
    if feed.URL != "http://science.reddit.com/.rss":
        log.debug("Got wrong URL in basic.conf!")
        return 0

    # Rate inherited from defaults
    if feed.rate != cfg.rate:
        log.debug("Got wrong rate (non-default): %d", feed.rate)
        return 0

    # Keep overriding default
    if feed.keep == cfg.keep:
        log.debug("Got wrong keep (default): %d", feed.keep)
        return 0

    if feed.keep != 40:
        log.debug("Got wrong keep (non-default): %d", feed.keep)
        return 0

    if cfg.errors:
        log.debug("Good config but cfg.errors")
        return 0

    return 1

def test_bad_basic():
    # Test basic config
    cfg = config.CantoConfig("tests/bad/basic.conf", FEED_SHELF)

    cfg.parse()

    # Make sure non of the invalid feeds made it through
    if cfg.feeds:
        log.debug("Got feeds despite no URL!")
        return 0

    # Make sure we fell back to default for malformed.
    if type(cfg.rate) != int:
        log.debug("Rate poisoned.")
        return 0

    # Make sure cfg.errors is set
    if not cfg.errors:
        log.debug("Bad config, but !cfg.errors")
        return 0

    return 1

def test():
    if not test_good_basic():
        log.debug("FAILED test_good_basic")
        return
    if not test_bad_basic():
        log.debug("FAILED test_bad_basic")
        return

    print "CONFIG TESTS PASSED"

def cleanup():
    pass
