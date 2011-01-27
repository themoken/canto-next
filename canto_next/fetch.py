# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from feed import allfeeds

from threading import Thread
import feedparser
import urlparse
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

        try:
            result = None
            # Passworded Feed
            if self.feed.username or self.feed.password:
                mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
                domain = urlparse.urlparse(self.feed.URL)[1]
                mgr.add_password(None, domain, self.feed.username,
                        self.feed.password)

                # Try Basic Authentication
                auth = urllib2.HTTPBasicAuthHandler(mgr)
                opener = urllib2.build_opener(auth)
                try:
                    result = feedparser.parse(opener.open(request))
                except:
                    # And, failing that, Digest Authentication
                    auth = urllib2.HTTPDigestAuthHandler(mgr)
                    opener = urllib2.build_opener(auth)
                    result = feedparser.parse(opener.open(request))

            # No password
            else:
                result = feedparser.parse(feedparser.urllib2.urlopen(request))

            self.feed.update_contents = result
        except Exception, e:
            log.error("ERROR: try to parse %s, got %s" % (self.feed.URL, e))
            self.feed.update_contents = None
            return

        # Interpret feedparser's bozo_exception, if there was an
        # error that resulted in no content, it's the same as
        # any other broken feed.

        if "bozo_exception" in self.feed.update_contents:
            if self.feed.update_contents["bozo_exception"] == urllib2.URLError:
                log.error("ERROR: couldn't grab %s : %s" %\
                        (self.feed.URL,\
                        self.feed.update_contents["bozo_exception"].reason))
                self.feed.update_contents = None
                return
            elif len(self.feed.update_contents["entries"]) == 0:
                log.error("No content in %s: %s" %\
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
    def __init__(self, shelf, conf):
        self.shelf = shelf
        self.conf = conf
        self.threads = []

    def needs_update(self, feed):
        if not feed.items:
            log.info("Empty feed, attempt to update.")
            return True

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

    def still_working(self, URL):
        for thread, workingURL in self.threads:
            if URL == workingURL:
                return True
        return False

    def fetch(self):
        for feed in self.conf.feeds:
            if not self.needs_update(feed):
                continue

            if self.still_working(feed.URL):
                continue

            thread = CantoFetchThread(feed)
            thread.start()
            log.debug("Started thread for feed %s" % feed.URL)
            self.threads.append((thread, feed.URL))

    def process(self):
        for thread, URL in self.threads:
            if thread.isAlive():
                continue
            thread.join()

            # Feed could've disappeared between
            # fetch() and process()

            feed = allfeeds.get_feed(URL)
            if feed:
                feed.index()

        self.threads = [ t for t in self.threads if t[0].isAlive() ]
