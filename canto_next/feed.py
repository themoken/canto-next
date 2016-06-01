# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .plugins import PluginHandler, Plugin
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
        try:
            return fn(*args)
        finally:
            wunlock_all()
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
        try:
            return fn(*args)
        finally:
            runlock_all()
    return _fl

# feed_objs to enforce
def rlock_feed_objs(objs):
    feed_lock.acquire_read()
    for feed in sorted(allfeeds.feeds.keys()):
        for obj in objs:
            if obj.URL == feed:
                obj.lock.acquire_read()
                break

def runlock_feed_objs(objs):
    for feed in sorted(allfeeds.feeds.keys()):
        for obj in objs:
            if obj.URL == feed:
                obj.lock.release_read()
                break
    feed_lock.release_read()

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

        self.last_update = 0

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

    def __str__(self):
        return "CantoFeed: %s" % self.name

    # Return { id : { attribute : value .. } .. }

    def get_attributes(self, items, attributes):
        r = {}

        d = self.shelf[self.URL]

        args = [ (dict_id(item)["ID"], item, attributes[item]) for item in items ]
        args.sort()

        got = [ (item["id"], item) for item in d["entries"] ]
        got.sort()

        for item, full_id, needed_attrs in args:
            while got and item > got[0][0]:
                got.pop(0)

            if got and got[0][0] == item:
                attrs = {}
                for a in needed_attrs:
                    if a == "description":
                        real = "summary"
                    else:
                        real = a

                    if real in got[0][1]:
                        attrs[a] = got[0][1][real]
                    else:
                        attrs[a] = ""
                r[full_id] = attrs
                got.pop(0)
            else:
                log.warn("item not found: %s" % item)
                r[full_id] = {}
                for a in needed_attrs:
                    r[full_id][a] = ""
                r[full_id]["title"] = "???"
        return r

    # Given an ID and a dict of attributes, update the disk.
    def set_attributes(self, items, attributes):

        self.lock.acquire_write()

        d = self.shelf[self.URL]

        items_to_remove = []
        tags_to_add = []

        for item in items:
            d_id = dict_id(item)["ID"]

            for d_item in d["entries"]:
                if d_id != d_item["id"]:
                    continue
                for a in attributes[item]:
                    d_item[a] = attributes[item][a]

                items_to_remove.append(d_item)
                tags_to_add += self._tag([d_item])

        self.shelf[self.URL] = d
        self.shelf.update_umod()

        self.lock.release_write()

        self._retag(items_to_remove, tags_to_add, [])

    def _item_id(self, item):
        return json.dumps({ "URL" : self.URL, "ID" : item["id"] })

    def _tag(self, items):
        tags_to_add = []

        for item in items:
            tags_to_add.append((item, "maintag:" + self.name))
            if "canto-tags" in item:
                for user_tag in item["canto-tags"]:
                    log.debug("index adding user tag: %s - %s", user_tag,item["id"])
                    tags_to_add.append((item, user_tag))

        return tags_to_add

    def _retag(self, items_to_remove, tags_to_add, tags_to_remove):
        feed_lock.acquire_read()
        tag_lock.acquire_write()

        for item in items_to_remove:
            alltags.remove_id(self._item_id(item))

        for item, tag in tags_to_add:
            alltags.add_tag(self._item_id(item), tag)

        for item, tag in tags_to_remove:
            alltags.remove_tag(self._item_id(item), tag)

        alltags.do_tag_changes()

        tag_lock.release_write()
        feed_lock.release_read()

    def _keep_olditem(self, olditem):
        ref_time = time.time()

        if "canto_update" not in olditem:
            olditem["canto_update"] = ref_time

        item_time = olditem["canto_update"]

        if "canto-state" in olditem:
            item_state = olditem["canto-state"]
        else:
            item_state = []

        if (ref_time - item_time) < self.keep_time:
            log.debug("Item not over keep_time (%d): %s", 
                    self.keep_time, olditem["id"])
        elif self.keep_unread and "read" not in item_state:
            log.debug("Keeping unread item: %s\n", olditem["id"])
        else:
            log.debug("Discarding: %s", olditem["id"])
            return False
        return True

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
            log.debug("Previous content not found for %s.", self.URL)
            old_contents = {"entries" : []}
        else:
            old_contents = self.shelf[self.URL]
            log.debug("Fetched previous content for %s.", self.URL)

        new_entries = []

        for i, item in enumerate(update_contents["entries"]):

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

            new_entries.append((i, item["id"], item))

        # Sort by string id
        new_entries.sort(key=lambda x: x[1])

        # Remove duplicates
        last_id = ""
        for x in new_entries[:]:
            if x[1] == last_id:
                new_entries.remove(x)
            else:
                last_id = x[1]

        old_entries = [ (i, item["id"], item) for (i, item) in enumerate(old_contents["entries"])]

        old_entries.sort(key=lambda x: x[1])

        keep_all = new_entries == []

        kept_entries = []

        for x in new_entries:

            # old_entry is really old, see if we should keep or discard

            while old_entries and x[1] > old_entries[0][1]:
                if keep_all or self._keep_olditem(old_entries[0][2]):
                    kept_entries.append(old_entries.pop(0))
                else:
                    old_entries.pop(0)

            # new entry and old entry match, move content over

            if old_entries and x[1] == old_entries[0][1]:
                olditem = old_entries.pop(0)[2]
                for key in olditem:
                    if key == "canto_update":
                        continue
                    elif key.startswith("canto"):
                        x[2][key] = olditem[key]

            # new entry is really new, tell everyone

            else:
                call_hook("daemon_new_item", [self, x[2]])

        # Resort lists by place, instead of string id
        new_entries.sort()
        old_entries.sort()

        if keep_all:
            kept_entries += old_entries
        else:
            for x in old_entries:
                if self._keep_olditem(x[2]):
                    kept_entries.append(x)

        kept_entries.sort()
        new_entries += kept_entries

        update_contents["entries"] = [ x[2] for x in new_entries ]

        tags_to_add = self._tag(update_contents["entries"])
        tags_to_remove = []
        remove_items = []

        # Allow plugins to add items prior to running the editing functions
        # so that the editing functions are guaranteed the full list.

        for attr in list(self.plugin_attrs.keys()):
            if not attr.startswith("additems_"):
                continue

            try:
                a = getattr(self, attr)
                tags_to_add, tags_to_remove, remove_items = a(self, update_contents, tags_to_add, tags_to_remove, remove_items)
            except:
                log.error("Error running feed item adding plugin")
                log.error(traceback.format_exc())

        # Allow plugins DaemonFeedPlugins defining edit_* functions to have a
        # crack at the contents before we commit to disk.

        for attr in list(self.plugin_attrs.keys()):
            if not attr.startswith("edit_"):
                continue

            try:
                a = getattr(self, attr)
                tags_to_add, tags_to_remove, remove_items = a(self, update_contents, tags_to_add, tags_to_remove, remove_items)
            except:
                log.error("Error running feed editing plugin")
                log.error(traceback.format_exc())

        if not self.stopped:
            # Commit the updates to disk.

            self.shelf[self.URL] = update_contents

            self.lock.release_write()

            self._retag(old_contents["entries"] + remove_items, tags_to_add, tags_to_remove)
        else:
            self.lock.release_write()

    def destroy(self):
        # Check for existence in case of delete quickly
        # after add.

        self.stopped = True
        if self.URL in self.shelf:
            del self.shelf[self.URL]
