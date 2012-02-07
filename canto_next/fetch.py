# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .plugins import PluginHandler, Plugin
from .feed import allfeeds

from threading import Thread
import feedparser
import traceback
import urllib.parse
import urllib.request, urllib.error, urllib.parse
import logging
import time

log = logging.getLogger("CANTO-FETCH")

class DaemonFetchThreadPlugin(Plugin):
    pass

# This is the first time I've ever had a need for multiple inheritance.
# I'm not sure if that's a good thing or not =)

class CantoFetchThread(PluginHandler, Thread):
    def __init__(self, feed):
        PluginHandler.__init__(self)
        Thread.__init__(self)
        self.daemon = True

        self.plugin_class = DaemonFetchThreadPlugin
        self.update_plugin_lookups()

        self.feed = feed

    def run(self):
        request = urllib.request.Request(self.feed.URL)
        request.add_header('User-Agent',\
                'Canto/0.8.0 + http://codezen.org/canto')

        try:
            result = None
            # Passworded Feed
            if self.feed.username or self.feed.password:
                mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                domain = urllib.parse.urlparse(self.feed.URL)[1]
                mgr.add_password(None, domain, self.feed.username,
                        self.feed.password)

                # Try Basic Authentication
                auth = urllib.request.HTTPBasicAuthHandler(mgr)
                opener = urllib.request.build_opener(auth)
                try:
                    result = feedparser.parse(opener.open(request))
                except:
                    # And, failing that, Digest Authentication
                    auth = urllib.request.HTTPDigestAuthHandler(mgr)
                    opener = urllib.request.build_opener(auth)
                    result = feedparser.parse(opener.open(request))

            # No password
            else:
                result = feedparser.parse(feedparser.urllib2.urlopen(request))

            self.feed.update_contents = result
        except Exception as e:
            log.error("ERROR: try to parse %s, got %s" % (self.feed.URL, e))
            self.feed.update_contents = None
            return

        # Interpret feedparser's bozo_exception, if there was an
        # error that resulted in no content, it's the same as
        # any other broken feed.

        if "bozo_exception" in self.feed.update_contents:
            if self.feed.update_contents["bozo_exception"] == urllib.error.URLError:
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

        # Allow DaemonFetchThreadPlugins to do any sort of fetch stuff
        # before the thread is marked as complete.

        for attr in list(self.plugin_attrs.keys()):
            if not attr.startswith("fetch_"):
                continue

            try:
                a = getattr(self, attr)
                a(feed = self.feed, newcontent = self.feed.update_contents)
            except:
                log.error("Error running fetch thread plugin")
                log.error(traceback.format_exc())

        log.debug("Plugins complete.")

class CantoFetch():
    def __init__(self, shelf):
        self.shelf = shelf
        self.threads = []

    def needs_update(self, feed):
        if not feed.items:
            log.info("Empty feed, attempt to update.")
            return True

        needs_update = True
        if feed.URL in self.shelf:
            f = self.shelf[feed.URL]

            passed = time.time() - f["canto_update"]
            if passed < feed.rate * 60:
                log.debug("Not enough time passed on %s (only %sm)" %
                        (feed.URL, passed / 60))
                needs_update = False

        return needs_update

    def still_working(self, URL):
        for thread, workingURL in self.threads:
            if URL == workingURL:
                return True
        return False

    def fetch(self, force):
        for feed in allfeeds.get_feeds():
            if not force and not self.needs_update(feed):
                continue

            if self.still_working(feed.URL):
                continue

            thread = CantoFetchThread(feed)
            thread.start()
            log.debug("Started thread for feed %s" % feed.URL)
            self.threads.append((thread, feed.URL))

    def process(self):
        newthreads = []

        for thread, URL in self.threads:
            if thread.isAlive():
                newthreads.append((thread, URL))
                continue
            thread.join()

            # Feed could've disappeared between
            # fetch() and process()

            feed = allfeeds.get_feed(URL)
            if feed:
                feed.index()

        self.threads = newthreads
