# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .plugins import PluginHandler, Plugin
from .encoding import encoder
from .tag import alltags
from .rwlock import RWLock, read_lock, write_lock
from .locks import feed_lock, tag_lock
from .hooks import call_hook

import traceback
import logging
import json
import time

log = logging.getLogger("FEED")

def dict_id(i):
    if type(i) == dict:
        return i
    return json.loads(i)

class CantoFeeds():
    def __init__(self):
        self.order = []
        self.feeds = {}
        self.dead_feeds = {}

    @write_lock(feed_lock)
    def add_feed(self, URL, feed):
        self.order.append(URL)
        self.feeds[URL] = feed

        # Return old feed object
        if URL in self.dead_feeds:
            del self.dead_feeds[URL]

    @read_lock(feed_lock)
    def get_feed(self, URL):
        if URL in self.feeds:
            return self.feeds[URL]
        if URL in self.dead_feeds:
            return self.dead_feeds[URL]

    @read_lock(feed_lock)
    def get_feeds(self):
        return [ self.get_feed(URL) for URL in self.order]

    @read_lock(feed_lock)
    def items_to_feeds(self, items):
        f = {}
        for i in items:
            d_i = dict_id(i)

            if d_i["URL"] in self.feeds:
                feed = self.feeds[d_i["URL"]]
            else:
                raise Exception("Can't find feed: %s" % d_i["URL"])

            if feed in f:
                f[feed].append(i)
            else:
                f[feed] = [i]
        return f

    def all_parsed(self):
        for URL in self.dead_feeds:
            feed = self.dead_feeds[URL]
            call_hook("daemon_del_tag", [[ "maintag:" + feed.name ]])
            feed.destroy()
        self.dead_feeds = {}

    @write_lock(feed_lock)
    def reset(self):
        self.dead_feeds = self.feeds
        self.feeds = {}
        self.order = []

allfeeds = CantoFeeds()

# Lock helpers

def wlock_all():
    feed_lock.acquire_write()
    for feed in sorted(allfeeds.feeds.keys()):
        allfeeds.feeds[feed].lock.acquire_write()

def wunlock_all():
    for feed in sorted(allfeeds.feeds.keys()):
        allfeeds.feeds[feed].lock.release_write()
    feed_lock.release_write()

def wlock_feeds(fn):
    def _fl(*args):
        wlock_all()
        r = fn(*args)
        wunlock_all()
        return r
    return _fl

def rlock_all():
    feed_lock.acquire_read()
    for feed in sorted(allfeeds.feeds.keys()):
        allfeeds.feeds[feed].lock.acquire_read()

def runlock_all():
    for feed in sorted(allfeeds.feeds.keys()):
        allfeeds.feeds[feed].lock.release_read()
    feed_lock.release_read()

def rlock_feeds(fn):
    def _fl(*args):
        rlock_all()
        r = fn(*args)
        runlock_all()
        return r
    return _fl

def stop_feeds():
    for feed in allfeeds.feeds:
        allfeeds.feeds[feed].stopped = True

class DaemonFeedPlugin(Plugin):
    pass

class CantoFeed(PluginHandler):
    def __init__(self, shelf, name, URL, rate, keep_time, keep_unread, **kwargs):
        PluginHandler.__init__(self)

        self.plugin_class = DaemonFeedPlugin
        self.update_plugin_lookups()

        self.shelf = shelf
        self.name = name
        self.URL = URL
        self.rate = rate
        self.keep_time = keep_time
        self.keep_unread = keep_unread
        self.stopped = False

        # This is held by the update thread, as well as any get / set attribute
        # threads

        self.lock = RWLock()

        self.username = None
        if "username" in kwargs:
            self.username = kwargs["username"]

        self.password = None
        if "password" in kwargs:
            self.password = kwargs["password"]

        allfeeds.add_feed(URL, self)

    # Identify items that are no longer being recorded.

    def old_ids(self, olditems):
        r = []
        for olditem in olditems:
            for item in self.shelf[self.URL]["entries"]:
                if item["id"] == olditem["id"]:
                    break
            else:
                cache_id = self._cacheitem(olditem)["id"]
                r.append(cache_id)
        return r

    # Return { id : { attribute : value .. } .. }

    def get_attributes(self, items, attributes):
        r = {}

        d = self.shelf[self.URL]

        for item in items:
            d_id = dict_id(item)["ID"]
            attrs = {}

            for d_item in d["entries"]:
                if d_id != d_item["id"]:
                    continue

                for a in attributes[item]:
                    if a == "description":
                        real = "summary"
                    else:
                        real = a

                    if real in d_item:
                        attrs[a] = d_item[real]
                    else:
                        attrs[a] = ""
            r[item] = attrs
        return r

    # Given an ID and a dict of attributes, update the disk.
    def set_attributes(self, items, attributes):

        self.lock.acquire_write()

        d = self.shelf[self.URL]

        for item in items:
            d_id = dict_id(item)["ID"]

            for d_item in d["entries"]:
                if d_id != d_item["id"]:
                    continue

                for a in attributes[item]:
                    if a == "canto-tags":
                        # Sub in empty tags
                        if a not in d_item:
                            d_item[a] = []

                        for user_tag in d_item[a]:
                            if user_tag not in attributes[item][a]:
                                log.debug("set removing tag: %s - %s" % (user_tag, item))
                                alltags.remove_tag(item, user_tag)
                        for user_tag in attributes[item][a]:
                            if user_tag not in d_item[a]:
                                log.debug("set adding tag: %s - %s" % (user_tag, item))
                                alltags.add_tag(item, user_tag)

                    d_item[a] = attributes[item][a]

        self.shelf[self.URL] = d
        self.shelf.update_umod()

        self.lock.release_write()

    def _cacheitem(self, item):
        cacheitem = {}
        cacheitem["id"] = json.dumps(\
                { "URL" : self.URL, "ID" : item["id"] })
        return cacheitem

    # Re-index contents
    # If we have update_contents, use that
    # If not, at least populate self.items from disk.

    # MUST GUARANTEE self.items is in same order as entries on disk.

    def index(self, update_contents):

        # If the daemon is shutting down, discard this update.

        if self.stopped:
            return

        self.lock.acquire_write()

        if self.URL not in self.shelf:
            # Stub empty feed
            log.debug("Previous content not found for %s." % self.URL)
            old_contents = {"entries" : []}
        else:
            old_contents = self.shelf[self.URL]
            log.debug("Fetched previous content for %s." % self.URL)

        # BEWARE: At this point, update_contents could either be
        # fresh from feedparser or fresh from disk, so it's possible that the
        # old contents and the new contents are identical.

        # STEP 1: Identify all of the items in update_contents, and move
        # over any associated state from old_contents

        tags_to_add = []
        to_add = []

        for item in update_contents["entries"]:

            # Update canto_update only for freshly seen items.
            item["canto_update"] = update_contents["canto_update"]

            # Attempt to isolate a feed unique ID
            if "id" not in item:
                if "link" in item:
                    item["id"] = item["link"]
                elif "title" in item:
                    item["id"] = item["title"]
                else:
                    log.error("Unable to uniquely ID item: %s" % item)
                    continue

            # Make sure that this item can be uniquely IDed.
            found = False
            for seen_item in to_add:
                if seen_item["id"] == item["id"]:
                    found = True
                    break

            if found:
                continue

            to_add.append(item)

            cacheitem = self._cacheitem(item)
            tags_to_add.append((cacheitem["id"], "maintag:" + self.name))

            # Move over custom content from item.  Custom content is denoted
            # with a key that starts with "canto", but not "canto_update",
            # which changes invariably.

            for olditem in old_contents["entries"]:
                if item["id"] == olditem["id"]:
                    for key in olditem:
                        if key == "canto_update":
                            continue
                        if key == "canto-tags":
                            for user_tag in olditem[key]:
                                log.debug("index adding user tag: %s - %s" % (user_tag,item["id"]))
                                tags_to_add.append((item["id"], user_tag))
                            item[key] = olditem[key]
                        elif key.startswith("canto"):
                            item[key] = olditem[key]
                    break
            else:
                call_hook("daemon_new_item", [self, item])

        update_contents["entries"] = to_add

        # STEP 2: Keep all items that have been seen in the feed in the last
        # day (keep_time default).

        ref_time = time.time()
        for olditem in old_contents["entries"]:
            for item in to_add:
                if olditem["id"] == item["id"]:
                    break
            else:
                if "canto_update" not in olditem:
                    olditem["canto_update"] = ref_time

                item_time = olditem["canto_update"]

                if "canto-state" in olditem:
                    item_state = olditem["canto-state"]
                else:
                    item_state = []

                if (ref_time - item_time) < self.keep_time:
                    log.debug("Item not over keep_time (%d): %s" %
                            (self.keep_time, olditem["id"]))
                elif self.keep_unread and "read" not in item_state:
                    log.debug("Keeping unread item: %s\n" % olditem["id"])
                else:
                    log.debug("Discarding: %s", olditem["id"])
                    continue

                update_contents["entries"].append(olditem)

        # Allow plugins DaemonFeedPlugins defining edit_* functions to have a
        # crack at the contents before we commit to disk.

        for attr in list(self.plugin_attrs.keys()):
            if not attr.startswith("edit_"):
                continue

            try:
                a = getattr(self, attr)
                a(feed = self, newcontent = update_contents)
            except:
                log.error("Error running feed editing plugin")
                log.error(traceback.format_exc())

        if not self.stopped:
            # Commit the updates to disk.

            self.shelf[self.URL] = update_contents

            to_remove = self.old_ids(old_contents["entries"])

            self.lock.release_write()

            tag_lock.acquire_write()

            for item in to_remove:
                alltags.remove_id(item)

            for item, tag in tags_to_add:
                alltags.add_tag(item, tag)

            # Go through and take items in old_contents that didn't make it
            # into update_contents / self.items and remove them from all tags.


            tag_lock.release_write()
        else:
            self.lock.release_write()

    def destroy(self):
        # Check for existence in case of delete quickly
        # after add.

        if self.URL in self.shelf:
            del self.shelf[self.URL]
