# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from threading import Thread
import feedparser
import urllib2
import logging
import time

log = logging.getLogger("CANTO-FETCH")

class CantoFetchThread(Thread):
    def __init__(self, feed):
        Thread.__init__(self)
        self.feed = feed

    def run(self):
        request = urllib2.Request(self.feed.URL)
        request.add_header('User-Agent',\
                'Canto/0.8.0 + http://codezen.org/canto')

        # Handle non-password, non-script, non-file URLs
        try:
            self.feed.feedparsed = feedparser.parse(\
                    feedparser.urllib2.urlopen(request))
        except Exception, e:
            log.info("ERROR: try to parse %s, got %s" % (self.feed.URL, e))
            self.feed.feedparsed = None
            return

        # Interpret feedparser's bozo_exception, if there was an
        # error that resulted in no content, it's the same as
        # any other broken feed.

        if "bozo_exception" in self.feed.feedparsed:
            if self.feed.feedparsed["bozo_exception"] == urllib2.URLError:
                log.info("ERROR: couldn't grab %s : %s" %\
                        (self.feed.URL,\
                        self.feed.feedparsed["bozo_exception"].reason))
                self.feed.feedparsed = None
                return
            elif len(self.feed.feedparsed["entries"]) == 0:
                log.info("No content in %s: %s" %\
                        (self.feed.URL,\
                        self.feed.feedparsed["bozo_exception"]))
                self.feed.feedparsed = None
                return

            # Replace it if we ignore it, since exceptions
            # are not pickle-able.
            self.feed.feedparsed["bozo_exception"] = None

        # Update timestamp
        self.feed.feedparsed["canto_update"] = time.time()

        log.info("Parsed %s" % self.feed.URL)

class CantoFetch():
    def __init__(self, shelf, feeds):
        self.shelf = shelf
        self.feeds = feeds

    def fetch(self):
        self.threads = []
        for feed in self.feeds:
            if feed.URL in self.shelf:
                f = self.shelf[feed.URL]

                # If not enough time has passed, don't bother
                # starting up a thread.
                passed = time.time() - f["canto_update"]
                if passed < feed.rate * 60:
                    log.debug("Not enough time passed on %s (only %sm)" %
                            (feed.URL, passed / 60))
                    continue

            thread = CantoFetchThread(feed)
            thread.start()
            log.debug("Started thread for feed %s" % feed.URL)
            self.threads.append((thread, feed))

    def process(self):
        for thread, feed in self.threads:
            thread.join()

            # Skip any errored feeds
            if not feed.feedparsed:
                continue

            self.shelf[feed.URL] = feed.feedparsed
