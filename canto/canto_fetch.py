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
            self.feed.update_contents = feedparser.parse(\
                    feedparser.urllib2.urlopen(request))
        except Exception, e:
            log.info("ERROR: try to parse %s, got %s" % (self.feed.URL, e))
            self.feed.update_contents = None
            return

        # Interpret feedparser's bozo_exception, if there was an
        # error that resulted in no content, it's the same as
        # any other broken feed.

        if "bozo_exception" in self.feed.update_contents:
            if self.feed.update_contents["bozo_exception"] == urllib2.URLError:
                log.info("ERROR: couldn't grab %s : %s" %\
                        (self.feed.URL,\
                        self.feed.update_contents["bozo_exception"].reason))
                self.feed.update_contents = None
                return
            elif len(self.feed.update_contents["entries"]) == 0:
                log.info("No content in %s: %s" %\
                        (self.feed.URL,\
                        self.feed.update_contents["bozo_exception"]))
                self.feed.update_contents = None
                return

            # Replace it if we ignore it, since exceptions
            # are not pickle-able.

            self.feed.update_contents["bozo_exception"] = None

        # Update timestamp
        self.feed.update_contents["canto_update"] = time.time()

        log.debug("Parsed %s" % self.feed.URL)

class CantoFetch():
    def __init__(self, shelf, feeds):
        self.shelf = shelf
        self.feeds = feeds
        self.threads = []

    def needs_update(self, feed):
        needs_update = True

        self.shelf.open()
        if feed.URL in self.shelf:
            f = self.shelf[feed.URL]

            passed = time.time() - f["canto_update"]
            if passed < feed.rate * 60:
                log.debug("Not enough time passed on %s (only %sm)" %
                        (feed.URL, passed / 60))
                needs_update = False

        self.shelf.close()
        return needs_update

    def fetch(self):
        self.threads = []
        for feed in self.feeds:
            # If feed doesn't need an update, don't fire off a thread.
            if not self.needs_update(feed):
                continue

            thread = CantoFetchThread(feed)
            thread.start()
            log.debug("Started thread for feed %s" % feed.URL)
            self.threads.append((thread, feed))

    # Return whether all the threads are ready for reaping.
    def threads_ready(self):
        for thread, feed in self.threads:
            if thread.isAlive():
                return False
        return True

    def process(self):
        for thread, feed in self.threads:
            thread.join()

            # Skip any errored feeds
            if not feed.update_contents:
                continue

            self.shelf.open()
            self.shelf[feed.URL] = feed.update_contents
            self.shelf.close()
            feed.update_contents = None
