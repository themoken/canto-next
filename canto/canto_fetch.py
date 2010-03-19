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

        log.info("Parsed %s" % self.feed.URL)

class CantoFetch():
    def __init__(self, shelf, feeds):
        self.shelf = shelf
        self.feeds = feeds

    def fetch(self):
        threads = []
        for feed in self.feeds:
            thread = CantoFetchThread(feed)
            thread.start()
            log.debug("Started thread for feed %s" % feed.URL)
            threads.append(thread)

        for thread in threads:
            thread.join()
