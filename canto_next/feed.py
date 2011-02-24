# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from protect import protection
from tag import alltags
import logging

log = logging.getLogger("FEED")

class CantoFeeds():
    def __init__(self):
        self.feeds = {}
        self.dead_feeds = {}

    def add_feed(self, URL, feed):
        self.feeds[URL] = feed
        if URL in self.dead_feeds:
            del self.dead_feeds[URL]

    def get_feed(self, URL):
        if URL in self.feeds:
            return self.feeds[URL]
        if URL in self.dead_feeds:
            return self.dead_feeds[URL]

    def items_to_feeds(self, items):
        f = {}
        for i in items:
            if i[0] in self.feeds:
                feed = self.feeds[i[0]]
            elif i[0] in self.dead_feeds:
                feed = self.dead_feeds[i[0]]
            else:
                raise Exception("Can't find feed: %s" % i[0])

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

allfeeds = CantoFeeds()

class CantoFeed():
    def __init__(self, shelf, name, URL, rate, keep, **kwargs):
        allfeeds.add_feed(URL, self)
        self.shelf = shelf
        self.name = name
        self.URL = URL
        self.rate = rate
        self.keep = keep

        self.username = None
        if "username" in kwargs:
            self.username = kwargs["username"]

        self.password = None
        if "password" in kwargs:
            self.password = kwargs["password"]

        self.update_contents = None
        self.items = []
        self.olditems = []

        # Pull items from disk on instantiation.
        self.index()

    # Return whether item, if added, would have a unique ID
    def unique_item(self, item):
        for cur_item in self.items:
            # Just the non-URL part will match
            if cur_item["id"][1] == item["id"]:
                return False
        return True

    # Remove old items from all tags.
    def clear_tags(self):
        for olditem in self.olditems:
            for item in self.items:
                # Same ID exists in new items
                if item["id"] == olditem["id"]:
                    break
            else:
                alltags.remove_id(olditem["id"])

    def lookup_by_id(self, i):
        for idx, ci in enumerate(self.items):
            if ci["id"] == i:
                return (ci, idx)
        else:
            raise Exception, "%s not found in self.items" % (i,)

    # Return { attribute : value ... }
    def get_feedattributes(self, attributes):
        self.shelf.open()
        d = self.shelf[self.URL]
        self.shelf.close()

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
                        self.shelf.open()
                        d = self.shelf[self.URL]
                        self.shelf.close()

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

        self.shelf.open()
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
        self.shelf.close()

    # Re-index contents
    # If we have self.update_contents, use that
    # If not, at least populate self.items from disk.

    # MUST GUARANTEE self.items is in same order as entries on disk.

    def index(self):

        if not self.update_contents:
            self.shelf.open()
            try:
                if not self.items and self.URL in self.shelf:
                    self.update_contents = self.shelf[self.URL]
                else:
                    # No update yet, no disk presence, nothing to do
                    return
            finally:
                self.shelf.close()

        self.shelf.open()
        if self.URL not in self.shelf:
            # Stub empty feed
            log.debug("Previous content not found.")
            self.old_contents = {"entries" : []}
        else:
            self.old_contents = self.shelf[self.URL]
            log.debug("Fetched previous content.")
        self.shelf.close()

        # BEWARE: At this point, update_contents could either be
        # fresh from feedparser or fresh from disk, so it's possible that the
        # old contents and the new contents are identical.

        self.olditems = self.items
        self.items = []
        for item in self.update_contents["entries"]:

            # Attempt to isolate a feed unique ID
            if "id" not in item:
                if "link" in item:
                    item["id"] = item["link"]
                elif "title" in item:
                    item["id"] = item["title"]
                else:
                    log.error("Unable to uniquely ID item: %s" % item)
                    continue

            # Ensure ID truly is feed (and thus globally, since the
            # ID is paired with the unique URL) unique.

            if not self.unique_item(item):
                continue

            # At this point, we're sure item's going to be added.

            cacheitem = {}
            cacheitem["id"] = (self.URL, item["id"])

            alltags.add_tag(cacheitem["id"], self.name)

            # Move over custom content from item.
            # Custom content is denoted with a key that
            # starts with "canto", but not "canto_update",
            # which changes invariably.

            for olditem in self.old_contents["entries"]:
                if item["id"] == olditem["id"]:
                    for key in olditem:
                        if key == "canto_update":
                            continue
                        elif key.startswith("canto"):
                            item[key] = olditem[key]

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

        for i, olditem in enumerate(self.olditems):
            for item in self.items:
                if olditem["id"] == item["id"]:
                    log.debug("still in self.items")
                    break
            else:
                if protection.protected(olditem["id"]):
                    log.debug("Saving committed item: %s" % olditem)
                    self.items.append(olditem)
                    self.update_contents["entries"].append(\
                            self.old_contents["entries"][i])
                else:
                    unprotected_old.append((i, olditem))

        # Flesh out the kept items so that we save 2x the number of items
        # presented in the feed naturally. This is particularly geared
        # towards bouncy feeds (like Reddit) where an item can fade in and
        # out of the feed and we don't want to worry about forgetting the
        # state.

        fill = min((2 * len(self.update_contents["entries"])) -
                len(self.items), len(unprotected_old))

        if fill > 0:
            log.debug("Saving %d old items to fill out disk" % fill)
            for idx, item in unprotected_old[:fill - 1]:
                self.update_contents["entries"].append(\
                        self.old_contents["entries"][idx])
                self.items.append(item)

        # Commit the updates to disk.
        self.shelf.open()
        self.shelf[self.URL] = self.update_contents
        self.shelf.close()

        # Remove non-existent IDs from all tags
        self.clear_tags()

        # No more updates
        self.update_contents = None

    def destroy(self):
        self.shelf.open()

        # Check for existence in case of delete quickly
        # after add.

        if self.URL in self.shelf:
            del self.shelf[self.URL]

        self.shelf.close()
