# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from tag import alltags
import logging

log = logging.getLogger("FEED")

allfeeds = {}

class CantoFeed():
    def __init__(self, shelf, name, URL, rate, keep):
        allfeeds[URL] = self
        self.shelf = shelf
        self.name = name
        self.URL = URL
        self.rate = rate
        self.keep = keep

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

    # Return { id : { attribute : value .. } .. }
    def get_attributes(self, i, attributes):
        atts = {}

        # Grab cached item
        for idx, ci in enumerate(self.items):
            if ci["id"] == i:
                item_cache = ci
                item_idx = idx
                break
        else:
            raise Exception, "%s not found in self.items" % (i,)

        # Get attributes
        for a in attributes:

            # Cached attribute
            if a in item_cache:
                atts[a] = ci[a]

            # Disk attribute
            else:
                self.shelf.open()
                d = self.shelf[self.URL]
                self.shelf.close()

                # NOTE: This relies on self.items maintaining
                # the identical order to the entries on disk.
                # Must be enforced by self.index()

                disk_item = d["entries"][item_idx]
                if a in disk_item:
                    atts[a] = disk_item[a]
                else:
                    atts[a] = ""
        return atts

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

        # Commit the updates to disk.
        self.shelf.open()
        self.shelf[self.URL] = self.update_contents
        self.shelf.close()

        # Remove non-existent IDs from all tags
        self.clear_tags()

        # No more updates
        self.update_contents = None
