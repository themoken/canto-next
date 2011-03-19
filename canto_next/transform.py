# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from feed import allfeeds

import logging
import re

log = logging.getLogger("TRANSFORM")

transform_locals = { }

# A Transform is generically any form of manipulation of the number of items
# (filter) or order of those items (sort) based on some criteria.

# The CantoTransform class serves as the base of all Transforms. It takes the
# elements returned by a class' `needed_attributes()`, populates a dict of
# these elements from cache/disk, and then gives them to the `transform()` call.

class CantoTransform():
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __call__(self, tag):
        a = {}
        f = allfeeds.items_to_feeds(tag)
        needed = self.needed_attributes(tag)

        for feed in f:
            attrs = {}
            for i in f[feed]:
                attrs[i] = needed
            a.update(feed.get_attributes(f[feed], attrs))
        return self.transform(tag, a)

    def needed_attributes(self, tag):
        return []

    def transform(self, items, attrs):
        return items

# A StateFilter will filter out items that match a particular state. Supports
# using "-tag" to indicate to filter out those missing the tag.

class StateFilter(CantoTransform):
    def __init__(self, state):
        CantoTransform.__init__(self, "Filter state: %s" % state)
        self.state = state

    def needed_attributes(self, tag):
        return ["canto-state"]

    def transform(self, items, attrs):
        if self.state[0] == "-":
            state = self.state[1:]
            keep = True
        else:
            state = self.state
            keep = False

        return [ i for i in items if \
                (state in attrs[i]["canto-state"]) == keep]

# Filter out items whose [attribute] content matches an arbitrary regex.

class ContentFilterRegex(CantoTransform):
    def __init__(self, attribute, regex):
        CantoTransform.__init__(self, "Filter %s in %s" % (attribute, regex))
        self.attribute = attribute
        try:
            self.match = re.compile(regex)
        except:
            self.match = None
            log.error("Couldn't compile regex: %s" % regex)

    def needed_attributes(self, tag):
        if not self.match:
            return []
        return [ self.attribute ]

    def transform(self, items, attrs):
        if not self.match:
            return item

        r = []
        for item in items:
           a = attrs[item]
           if self.attribute not in a:
               r.append(item)
               continue
           if type(a[self.attribute]) != unicode:
               log.error("Can't match non-string!")
               continue

           if not self.match.match(a[self.attribute]):
               r.append(item)
        return r

# Simple basic-string abstraction of the above.

class ContentFilter(ContentFilterRegex):
    def __init__(self, attribute, string):
        string = ".*" + re.escape(string) + ".*"
        ContentFilterRegex.__init__(self, attribute, string)

class SortTransform(CantoTransform):
    def __init__(self, name, attr, sortfunc = None):
        CantoTransform.__init__(self, name)
        self.attr = attr
        self.sort = sortfunc

    def needed_attributes(self, tag):
        return [ self.attr ]

    def transform(self, items, attrs):
        r = [ ( attrs[item][self.attr], item ) for item in items ]
        r.sort(self.sort)
        return [ item[1] for item in r ]

# Transform_locals is a list of elements that we pass to the eval() call when
# evaluating a transform line from the config. Passing these into the local
# scope allows simple filters to be created on the fly.

transform_locals["StateFilter"] = StateFilter
transform_locals["ContentFilterRegex"] = ContentFilterRegex
transform_locals["ContentFilter"] = ContentFilter
transform_locals["filter_read"] = StateFilter("read")
transform_locals["sort_alphabetical"] =\
        SortTransform("Sort Alphabetical", "title")

# So now lines line `global_transform = ContentFilter('title', 'AMA')` can be
# simply, safely, parsed with the Python interpreter. As well as supporting the
# simple syntax `global_transform = filter_read` etc.

# This code will throw an exception if it's invalid, so calling code must be
# prepared.

def eval_transform(transform_name):
    return eval(transform_name, {}, transform_locals)
