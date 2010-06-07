#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging

log = logging.getLogger("TAG")

class CantoTags():
    def __init__(self):
        self.tags = {}

    def add_tag(self, id, name):
        # Create tag if no tag exists
        if name not in self.tags:
            self.tags[name] = set()

        # Add to tag.
        self.tags[name].add(id)

    def remove_id(self, id):
        for tag in self.tags:
            if id in self.tags[tag]:
                self.tags[tag].remove(id)

    def get_tag(self, tag):
        if tag in self.tags.keys():
            return self.tags[tag]
        return []

    def reset(self):
        self.tags = {}

alltags = CantoTags()
