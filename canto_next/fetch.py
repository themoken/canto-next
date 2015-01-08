# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2014 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .plugins import PluginHandler, Plugin
from .feed import allfeeds
from .hooks import call_hook

from threading import Thread
import feedparser
import traceback
import urllib.parse
import urllib.request, urllib.error, urllib.parse
import logging
import socket
import json
import time

log = logging.getLogger("CANTO-FETCH")

class DaemonFetchThreadPlugin(Plugin):
    pass

# This is the first time I've ever had a need for multiple inheritance.
# I'm not sure if that's a good thing or not =)

class CantoFetchThread(PluginHandler, Thread):
    def __init__(self, feed, fromdisk):
        PluginHandler.__init__(self)
        Thread.__init__(self, name="Fetch: %s" % feed.URL)
        self.daemon = True

        self.plugin_class = DaemonFetchThreadPlugin
        self.update_plugin_lookups()

        # feedparser honors this value, want to avoid hung feeds when the
        # internet connection is flaky

        socket.setdefaulttimeout(30)

        self.feed = feed
        self.fromdisk = fromdisk

    def run(self):

        # Initial load, just feed.index grab from disk.

        if self.fromdisk:
            self.feed.index({"entries" : []})
            return

        self.feed.last_update = time.time()

        # Otherwise, actually try to get an update.

        extra_headers = { 'User-Agent' :\
                'Canto/0.9.0 + http://codezen.org/canto-ng'}

        try:
            result = None
            # Passworded Feed
            if self.feed.username or self.feed.password:
                domain = urllib.parse.urlparse(self.feed.URL)[1]
                man = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                auth = urllib.request.HTTPBasicAuthHandler(man)
                auth.handler_order = 490
                auth.add_password(None, domain, self.feed.username,
                        self.feed.password)

                try:
                    result = feedparser.parse(self.feed.URL, handlers=[auth],
                            request_headers = extra_headers)
                except:
                    # And, failing that, Digest Authentication
                    man = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                    auth = urllib.request.HTTPDigestAuthHandler(man)
                    auth.handler_order = 490
                    auth.add_password(None, domain, self.feed.username,
                            self.feed.password)
                    result = feedparser.parse(self.feed.URL, handlers=[auth],
                            request_headers = extra_headers)

            # No password
            else:
                result = feedparser.parse(self.feed.URL,
                        request_headers = extra_headers)

            update_contents = result
        except Exception as e:
            log.error("ERROR: try to parse %s, got %s" % (self.feed.URL, e))
            return

        # Interpret feedparser's bozo_exception, if there was an
        # error that resulted in no content, it's the same as
        # any other broken feed.

        if "bozo_exception" in update_contents:
            if update_contents["bozo_exception"] == urllib.error.URLError:
                log.error("ERROR: couldn't grab %s : %s" %\
                        (self.feed.URL,\
                        update_contents["bozo_exception"].reason))
                return
            elif len(update_contents["entries"]) == 0:
                log.error("No content in %s: %s" %\
                        (self.feed.URL,\
                        update_contents["bozo_exception"]))
                return

            # Replace it if we ignore it, since exceptions
            # are not pickle-able.

            update_contents["bozo_exception"] = None

        # Update timestamp
        update_contents["canto_update"] = self.feed.last_update

        update_contents = json.loads(json.dumps(update_contents))

        log.debug("Parsed %s" % self.feed.URL)

        # Allow DaemonFetchThreadPlugins to do any sort of fetch stuff
        # before the thread is marked as complete.

        for attr in list(self.plugin_attrs.keys()):
            if not attr.startswith("fetch_"):
                continue

            try:
                a = getattr(self, attr)
                a(feed = self.feed, newcontent = update_contents)
            except:
                log.error("Error running fetch thread plugin")
                log.error(traceback.format_exc())

        log.debug("Plugins complete.")

        # This handles it's own locking
        self.feed.index(update_contents)


class CantoFetch():
    def __init__(self, shelf):
        self.shelf = shelf
        self.threads = []

    def needs_update(self, feed):
        passed = time.time() - feed.last_update
        if passed < feed.rate * 60:
            return False
        return True

    def still_working(self, URL):
        for thread, workingURL in self.threads:
            if URL == workingURL:
                return True
        return False

    def fetch(self, force, fromdisk):
        for feed in allfeeds.get_feeds():
            if not force and not self.needs_update(feed):
                continue

            if self.still_working(feed.URL):
                continue

            thread = CantoFetchThread(feed, fromdisk)
            thread.start()
            log.debug("Started thread for feed %s" % feed.URL)
            self.threads.append((thread, feed.URL))

    def reap(self, force=False):
        work_done = False
        newthreads = []

        for thread, URL in self.threads:
            if not force and thread.isAlive():
                newthreads.append((thread, URL))
                continue
            work_done = True
            thread.join()

        self.threads = newthreads

        if work_done:
            if self.threads == []:
                self.shelf.sync()
            call_hook("daemon_work_done", [])
