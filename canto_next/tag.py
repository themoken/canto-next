#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .hooks import on_hook, call_hook
from .rwlock import read_lock, write_lock
from .locks import *

import logging

log = logging.getLogger("TAG")

class CantoTags():
    def __init__(self):
        self.tags = {}
        self.changed_tags = []

        # Per-tag transforms
        self.tag_transforms = {}

        # Extra tag map
        # This allows tags to be defined as parts of larger tags.  For example,
        # Penny Arcade and xkcd could both have the extra "comic" tag which
        # could then be used in a filter to implement categories.

        self.extra_tags = {}

    def items_to_tags(self, ids):
        tags = []
        for id in ids:
            for tag in self.tags:
                if id in self.tags[tag] and tag not in tags:
                    tags.append(tag)
        return tags

    def tag_changed(self, tag):
        if tag not in self.changed_tags:
            self.changed_tags.append(tag)

    def get_tag(self, tag):
        if tag in list(self.tags.keys()):
            return self.tags[tag]
        return []

    def get_tags(self):
        return list(self.tags.keys())

    def tag_transform(self, tag, transform):
        self.tag_transforms[tag] = transform

    def set_extra_tags(self, tag, extra_tags):
        self.extra_tags[tag] = extra_tags

    def clear_tags(self):
        self.tags = {}

    def reset(self):
        self.tag_transforms = {}
        self.extra_tags = {}

        # Don't set tag_changed here, because we don't want to alert when a tag
        # will probably just be re-populated with identical content.

        # It it isn't, then the add or remove will set it for us.

        self.clear_tags()

    #
    # Following must be called with tag_lock held with write
    #

    def add_tag(self, id, name):
        if name in self.extra_tags:
            extras = self.extra_tags[name]
        else:
            extras = []

        alladded = [ name ] + extras

        for name in alladded:
            # Create tag if no tag exists
            if name not in self.tags:
                self.tags[name] = []
                call_hook("daemon_new_tag", [[ name ]])

            # Add to tag.
            if id not in self.tags[name]:
                self.tags[name].append(id)
                self.tag_changed(name)

    def remove_tag(self, id, name):
        if name in self.tags and id in self.tags[name]:
            self.tags[name].remove(id)
            self.tag_changed(name)

    def remove_id(self, id):
        for tag in self.tags:
            if id in self.tags[tag]:
                self.tags[tag].remove(id)
                self.tag_changed(tag)

    def apply_transforms(self, tag, tagobj):
        from .config import config
        # Global transform
        if config.global_transform:
            tagobj = config.global_transform(tagobj)

        # Tag level transform
        if tag in self.tag_transforms and\
                self.tag_transforms[tag]:
            tagobj = self.tag_transforms[tag](tagobj)

        return tagobj

    def do_tag_changes(self):
        for tag in self.changed_tags:
            tagobj = self.get_tag(tag)

            try:
                tagobj = self.apply_transforms(tag, tagobj)
            except Exception as e:
                log.error("Exception applying transforms: %s" % e)

            self.tags[tag] = tagobj
            call_hook("daemon_tag_change", [ tag ])
        self.changed_tags = []

alltags = CantoTags()
