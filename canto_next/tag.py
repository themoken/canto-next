#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from hooks import call_hook

import logging

log = logging.getLogger("TAG")

class CantoTags():
    def __init__(self):
        self.oldtags = {}
        self.tags = {}

    def add_tag(self, id, name):
        # Create tag if no tag exists
        if name not in self.tags:
            self.tags[name] = []
            if name not in self.oldtags:
                call_hook("new_tag", [[ name ]])

        # Add to tag.
        if id not in self.tags[name]:
            self.tags[name].append(id)
            call_hook("tag_change", [name])

    def remove_id(self, id):
        for tag in self.tags:
            if id in self.tags[tag]:
                self.tags[tag].remove(id)
                call_hook("tag_change", [tag])

    def get_tag(self, tag):
        if tag in self.tags.keys():
            return self.tags[tag]
        return []

    def del_old_tags(self):
        oldtags = []
        for tag in self.oldtags:
            if tag not in self.tags:
                oldtags.append(tag)
        if oldtags:
            call_hook("del_tag", [ oldtags ])

    def reset(self):
        self.oldtags = self.tags
        self.tags = {}

        for tag in self.oldtags:
            call_hook("tag_change", [tag])

alltags = CantoTags()
