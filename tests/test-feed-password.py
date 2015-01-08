#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from base import *

from canto_next.feed import CantoFeed
from canto_next.fetch import CantoFetchThread

import feedparser
import urllib.parse
import urllib.request

TEST_URL="http://codezen.org/password-feed/canto.xml"
USER="test"
PASS="tester"

class TestFeedPassword(Test):
    def check(self):
        # First make sure that feedparser hasn't been broken

        domain = urllib.parse.urlparse(TEST_URL)[1]
        man = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        auth = urllib.request.HTTPBasicAuthHandler(man)
        auth.handler_order = 490 # Workaround feedparser issue #283
        auth.add_password(None, domain, USER, PASS)

        f = feedparser.parse(TEST_URL, handlers=[auth])

        if f["bozo"] == 1:
            raise Exception("feedparser is broken!")

        test_shelf = {}
        test_feed = CantoFeed(test_shelf, "Passworded Feed", TEST_URL, 10, 86400, False,
                password=PASS, username=USER)

        thread = CantoFetchThread(test_feed, False)
        thread.start()
        thread.join()

        if TEST_URL not in test_shelf:
            raise Exception("Canto failed to get passworded feed")

        return True

TestFeedPassword("feed password")
