# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .plugins import PluginHandler, Plugin
from .protect import protection
from .encoding import encoder
from .tag import alltags
from .rwlock import RWLock, read_lock, write_lock
from .locks import feed_lock, protect_lock, tag_lock
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
        r = None

        self.order.append(URL)
        self.feeds[URL] = feed

        # Return old feed object
        if URL in self.dead_feeds:
            r = self.dead_feeds[URL]
            del self.dead_feeds[URL]

        return r

    @read_lock(feed_lock)
    def get_feed(self, URL):
        if URL in self.feeds:
            return self.feeds[URL]
        if URL in self.dead_feeds:
            return self.dead_feeds[URL]

    @read_lock(feed_lock)
    def get_feeds(self):
        return [ self.get_feed(URL) for URL in self.order]

    # Interestingly, don't need to get the read lock on feed because the URL is
    # part of the ID.

    def items_to_feeds(self, items):
        f = {}
        for i in items:
            d_i = dict_id(i)

            if d_i["URL"] in self.feeds:
                feed = self.feeds[d_i["URL"]]
            elif d_i["URL"] in self.dead_feeds:
                feed = self.dead_feeds[d_i["URL"]]
            else:
                raise Exception("Can't find feed: %s" % d_i["URL"])

            if feed in f:
                f[feed].append(i)
            else:
                f[feed] = [i]
        return f

    def really_dead(self, feed):
        if feed.URL in self.dead_feeds:
            del self.dead_feeds[feed.URL]
        feed.destroy()

    def reset(self):
        self.dead_feeds = self.feeds
        self.feeds = {}
        self.order = []

allfeeds = CantoFeeds()

# Lock helpers

def wlock_all():
    feed_lock.acquire_read()
    for feed in sorted(allfeeds.feeds.keys()):
        allfeeds.feeds[feed].lock.acquire_write()

def wunlock_all():
    for feed in sorted(allfeeds.feeds.keys()):
        allfeeds.feeds[feed].lock.release_write()
    feed_lock.release_read()

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

        oldfeed = allfeeds.add_feed(URL, self)

        if oldfeed and oldfeed.items:
            self.items = oldfeed.items
            oldfeed.items = []
            for item in self.items:
                # Will not lock, Feeds() should only be instantiated holding
                # config, tag, and feed_lock.
                alltags.add_tag(item["id"], "maintag:" + self.name)
        else:
            self.items = []

    # Return whether item, if added, would have a unique ID. Called with
    # self.lock read.

    def unique_item(self, item):
        for cur_item in self.items:
            # Just the non-URL part will match
            if dict_id(cur_item["id"])["ID"] == item["id"]:
                return False
        return True

    # Remove old items from all tags. Called with self.lock read

    def sweep_tags(self, olditems):
        for olditem in olditems:
            for item in self.items:
                # Same ID exists in new items
                if item["id"] == olditem["id"]:
                    break
            else:
                # Will lock
                alltags.remove_id(olditem["id"])

    # Called with self.lock read

    def lookup_by_id(self, i):
        for idx, ci in enumerate(self.items):
            if ci["id"] == i:
                return (ci, idx)
        else:
            raise Exception("%s not found in self.items" % (i,))

    # Return { attribute : value ... }

    def get_feedattributes(self, attributes):

        d = self.shelf[self.URL]

        r = {}
        for attr in attributes:
            if attr in d:
                r[attr] = d[attr]
            else:
                r[attr] = ""

        return r

    # Return { id : { attribute : value .. } .. }

    def get_attributes(self, items, attributes):
        r = {}

        for i in items:
            attrs = {}

            # Grab cached item
            try:
                item_cache, item_idx = self.lookup_by_id(i)
            except:
                continue

            # Potential fetched disk data.
            d = None

            # Get attributes
            for a in attributes[i]:

                # Cached attribute
                if a in item_cache:
                    attrs[a] = ci[a]

                # Disk attribute
                else:

                    # If we haven't already grabbed the disk content, do so.
                    if not d:
                        d = self.shelf[self.URL]

                    # NOTE: This relies on self.items maintaining
                    # the identical order to the entries on disk.
                    # Must be enforced by self.index()

                    disk_item = d["entries"][item_idx]
                    if a in disk_item:
                        attrs[a] = disk_item[a]
                    else:
                        attrs[a] = ""
            r[i] = attrs

        return r

    # Given an ID and a dict of attributes, update the disk.
    def set_attributes(self, items, attributes):

        d = self.shelf[self.URL]

        for i in items:
            try:
                item_cache, item_idx = self.lookup_by_id(i)
            except:
                continue

            # NOTE: This relies on self.items maintaining
            # the identical order to the entries on disk.
            # Must be enforced by self.index()

            for a in attributes[i]:
                if a == "canto-tags":
                    # Sub in empty tags
                    if a not in d["entries"][item_idx]:
                        d["entries"][item_idx][a] = []

                    for user_tag in d["entries"][item_idx][a]:
                        if user_tag not in attributes[i][a]:
                            log.debug("set removing tag: %s - %s" % (user_tag, i))
                            alltags.remove_tag(i, user_tag)
                    for user_tag in attributes[i][a]:
                        if user_tag not in d["entries"][item_idx][a]:
                            log.debug("set adding tag: %s - %s" % (user_tag, i))
                            alltags.add_tag(i, user_tag)

                d["entries"][item_idx][a] = attributes[i][a]


        self.shelf[self.URL] = d

        # Allow DaemonFeed plugins to define set_attribute_* functions
        # to receive notifications of changed attributes

        for attr in list(self.plugin_attrs.keys()):
            if not attr.startswith("set_attributes_"):
                continue

            try:
                a = getattr(self, attr)
                a(feed = self, items = items, attributes = attributes, content = d)
            except:
                log.error("Error running feed set_attr plugin")
                log.error(traceback.format_exc())

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

        self.items = []
        tags_to_add = []

        for item in update_contents["entries"][:]:

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
                    update_contents["entries"].remove(item)
                    continue

            # Ensure ID truly is feed (and thus globally, since the
            # ID is paired with the unique URL) unique.

            if not self.unique_item(item):
                update_contents["entries"].remove(item)
                continue

            # At this point, we're sure item's going to be added.
            cacheitem = self._cacheitem(item)

            tags_to_add.append((cacheitem["id"], "maintag:" + self.name))

            # Move over custom content from item.
            # Custom content is denoted with a key that
            # starts with "canto", but not "canto_update",
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

            # Other cache-able values should be added here.

            self.items.append(cacheitem)

        # STEP 2: Keep items that have been given to clients from disappearing
        # from the disk. This ensures that even if an item has been sitting in
        # an active client for days requests for more information won't fail.

        # While we're looping through the olditems, we also make a list of
        # unprotected items for the next step (increasing the number of
        # remembered feed items).

        unprotected_old = []

        protect_lock.acquire_read()

        for olditem in old_contents["entries"]:
            for item in self.items:
                if olditem["id"] == item["id"]:
                    log.debug("still in self.items")
                    break
            else:
                if protection.protected(olditem["id"]):
                    log.debug("Saving committed item: %s" % olditem["id"])
                    self.items.append(self._cacheitem(olditem))
                    update_contents["entries"].append(olditem)
                else:
                    unprotected_old.append(olditem)

        protect_lock.release_read()

        # Keep all items that have been seen in the feed in the last day.

        ref_time = time.time()
        for olditem in unprotected_old:
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
            self.items.append(self._cacheitem(olditem))

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

            tag_lock.acquire_write()
            for item, tag in tags_to_add:
                alltags.add_tag(item, tag)

            # Go through and take items in old_contents that didn't make it
            # into update_contents / self.items and remove them from all tags.

            self.sweep_tags(old_contents["entries"])
            tag_lock.release_write()

        self.lock.release_write()

    def destroy(self):
        # Check for existence in case of delete quickly
        # after add.

        if self.URL in self.shelf:
            del self.shelf[self.URL]
