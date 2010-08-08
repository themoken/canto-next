# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from feed import allfeeds, items_to_feeds

import logging
import re

log = logging.getLogger("TRANSFORM")

transform_locals = { }

class CantoTransform():
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __call__(self, tag):
        a = {}
        f = items_to_feeds(tag)
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

        log.debug("attrs: %s" % attrs)
        return [ i for i in items if \
                (state in attrs[i]["canto-state"]) == keep]

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
        log.debug("returning: %s" % [ self.attribute ])
        return [ self.attribute ]

    def transform(self, items, attrs):
        log.debug("items: %s, attrs: %s" % (items, attrs))
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

class ContentFilter(ContentFilterRegex):
    def __init__(self, attribute, string):
        string = ".*" + re.escape(string) + ".*"
        ContentFilterRegex.__init__(self, attribute, string)

transform_locals["StateFilter"] = StateFilter
transform_locals["ContentFilter"] = ContentFilter
transform_locals["filter_read"] = StateFilter("read")

def eval_transform(transform_name):
    try:
        return eval(transform_name, {}, transform_locals)
    except Exception, e:
        import traceback
        tb = traceback.format_exc(e)
        log.error("Couldn't figure out transform: %s" % transform_name)
        log.error("\n" + "".join(tb))
        return None
