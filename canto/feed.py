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

allfeeds = []

class CantoFeed():
    def __init__(self, shelf, name, URL, rate, keep):
        allfeeds.append(self)
        self.shelf = shelf
        self.name = name
        self.URL = URL
        self.rate = rate
        self.keep = keep

        self.update_contents = None
        self.items = []
        self.olditems = []

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

    # Re-index contents
    def index(self):
        # We errored on the last update, bail
        if not self.update_contents:
            return

        self.shelf.open()
        if self.URL not in self.shelf:
            # Stub empty feed
            log.debug("Previous content not found.")
            self.old_contents = {"entries" : []}
        else:
            self.old_contents = self.shelf[self.URL]
            log.debug("Fetched previous content.")
        self.shelf.close()

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
