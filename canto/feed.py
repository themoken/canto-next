# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging

log = logging.getLogger("FEED")

class CantoFeed():
    def __init__(self, shelf, name, URL, rate, keep):
        self.shelf = shelf
        self.name = name
        self.URL = URL
        self.rate = rate
        self.keep = keep

        self.update_contents = None
        self.items = []

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

        self.items = []
        for item in self.update_contents["entries"]:
            cacheitem = {}
            cacheitem["id"] = (self.URL, item["id"])

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

        # No more updates
        self.update_contents = None
