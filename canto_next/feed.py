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
from .rwlock import RWLock
from .locks import protect_lock, tag_lock
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

    def add_feed(self, URL, feed):
        r = None

        self.order.append(URL)
        self.feeds[URL] = feed

        # Return old feed object
        if URL in self.dead_feeds:
            r = self.dead_feeds[URL]
            del self.dead_feeds[URL]

        return r

    def get_feed(self, URL):
        if URL in self.feeds:
            return self.feeds[URL]
        if URL in self.dead_feeds:
            return self.dead_feeds[URL]

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
            oldfeed.items = None
            for item in self.items:
                # Will not lock, Feeds() should only be instantiated holding
                # config, tag, and feed_lock.
                alltags._add_tag(item["id"], self.name, "maintag")
        else:
            self.items = []

    # Return whether item, if added, would have a unique ID
    def unique_item(self, item):
        for cur_item in self.items:
            # Just the non-URL part will match
            if dict_id(cur_item["id"])["ID"] == item["id"]:
                return False
        return True

    # Remove old items from all tags.
    def clear_tags(self, olditems):
        for olditem in olditems:
            for item in self.items:
                # Same ID exists in new items
                if item["id"] == olditem["id"]:
                    break
            else:
                # Will lock
                alltags.remove_id(olditem["id"])

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

    # Re-index contents
    # If we have update_contents, use that
    # If not, at least populate self.items from disk.

    # MUST GUARANTEE self.items is in same order as entries on disk.

    def index(self, update_contents):

        if not update_contents:
            if self.URL in self.shelf:
                update_contents = self.shelf[self.URL]

            # If we got nothing, and there's not anything already resident, at
            # least stub it in the shelf.

            else:
                update_contents = {"entries" : []}

        if self.URL not in self.shelf:
            # Stub empty feed
            log.debug("Previous content not found.")
            old_contents = {"entries" : []}
        else:
            old_contents = self.shelf[self.URL]
            log.debug("Fetched previous content.")

        # BEWARE: At this point, update_contents could either be
        # fresh from feedparser or fresh from disk, so it's possible that the
        # old contents and the new contents are identical.

        # We take our top level locks here and in specific order so that we
        # don't create a deadlock by holding self.lock and waiting on
        # tag/protect while the command holds tag/protect while trying to get
        # self.lock.

        protect_lock.acquire_read()
        tag_lock.acquire_write()
        self.lock.acquire_write()

        olditems = self.items
        self.items = []
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

            cacheitem = {}
            cacheitem["id"] = json.dumps(\
                    { "URL" : self.URL, "ID" : item["id"] } )

            # Will lock
            alltags.add_tag(cacheitem["id"], self.name, "maintag")

            # Move over custom content from item.
            # Custom content is denoted with a key that
            # starts with "canto", but not "canto_update",
            # which changes invariably.

            for olditem in old_contents["entries"]:
                if item["id"] == olditem["id"]:
                    for key in olditem:
                        if key == "canto_update":
                            continue
                        elif key.startswith("canto"):
                            item[key] = olditem[key]
                    break
            else:
                call_hook("daemon_new_item", [self, item])

            # Other cache-able values should be added here.

            self.items.append(cacheitem)

        # Keep items that have been given to clients from
        # disappearing from the disk. This ensures that even if
        # an item has been sitting in an active client for days
        # requests for more information won't fail.

        # While we're looping through the olditems, we also make a list of
        # unprotected items for the next step (increasing the number of
        # remembered feed items).

        unprotected_old = []

        for i, olditem in enumerate(olditems):
            for item in self.items:
                if olditem["id"] == item["id"]:
                    log.debug("still in self.items")
                    break
            else:
                if protection.protected(olditem["id"]):
                    log.debug("Saving committed item: %s" % olditem)
                    self.items.append(olditem)
                    update_contents["entries"].append(\
                            old_contents["entries"][i])
                else:
                    unprotected_old.append((i, olditem))

        protect_lock.release_read()

        # Keep all items that have been seen in the feed in the last day.

        ref_time = time.time()
        for idx, item in unprotected_old:
            # Old item
            if "canto_update" not in old_contents["entries"][idx]:
                old_contents["entries"][idx]["canto_update"] = ref_time
                log.debug("Subbing item time %s" % item)

            item_time = old_contents["entries"][idx]["canto_update"]
            if "canto-state" in old_contents["entries"][idx]:
                item_state = old_contents["entries"][idx]["canto-state"]
            else:
                item_state = []

            if (ref_time - item_time) < self.keep_time:
                log.debug("Item not over keep_time (%d): %s" %
                        (self.keep_time, item))
            elif self.keep_unread and "read" not in item_state:
                log.debug("Keeping unread item: %s\n" % item)
            else:
                log.debug("Discarding: %s", item)
                continue

            update_contents["entries"].append(\
                    old_contents["entries"][idx])
            self.items.append(item)

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

        # Commit the updates to disk.
        self.shelf[self.URL] = update_contents

        self.lock.release_write()

        # Remove non-existent IDs from all tags
        self.clear_tags(olditems)

        tag_lock.release_write()

    def destroy(self):
        # Check for existence in case of delete quickly
        # after add.

        if self.URL in self.shelf:
            del self.shelf[self.URL]
