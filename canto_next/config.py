# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .locks import feed_lock, config_lock, tag_lock, watch_lock
from .encoding import locale_enc
from .transform import eval_transform
from .feed import allfeeds, CantoFeed
from .tag import alltags

import traceback
import logging
import codecs
import json
import os
import re

log = logging.getLogger("CONFIG")

default_config =\
{
        "defaults" :
        {
            "rate" : 10,
            "keep_time" : 86400,
            "keep_unread" : False,
            "global_transform" : "filter_read"
        },

        "feeds" : [
            {
                "name" : "Canto",
                "url" : "http://codezen.org/canto-ng/feed/"
            },
            {
                "name" : "Slashdot",
                "url" : "http://rss.slashdot.org/slashdot/Slashdot"
            },
            {
                "name" : "Reddit",
                "url": "http://reddit.com/.rss"
            }
        ]
}

def parse_locks():
    config_lock.acquire_write()
    feed_lock.acquire_write()
    tag_lock.acquire_write()
    watch_lock.acquire_read()

def parse_unlocks():
    config_lock.release_write()
    feed_lock.release_write()
    tag_lock.release_write()
    watch_lock.release_read()

class CantoConfig():
    def init(self, filename, shelf):
        self.filename = filename
        self.shelf = shelf
        self.json = {}

        self.defaults_validators = [
                ("rate", self.validate_int, False),
                ("keep_time", self.validate_int, False),
                ("keep_unread", self.validate_bool, False),
                ("global_transform", self.validate_set_transform, False),
        ]

        self.defaults_defaults = {
                "rate" : 10,
                "keep_time" : 86400,
                "keep_unread" : False,
                "global_transform" : "None",
        }

        self.feed_validators = [
                ("name", self.validate_unique_feed_name, True),
                ("url", self.validate_unique_url, True),
                ("rate", self.validate_int, False),
                ("keep_time", self.validate_int, False),
                ("keep_unread", self.validate_bool, False),
                ("username", self.validate_string, False),
                ("password", self.validate_string, False),
        ]

        self.feed_defaults = {}

        self.tag_validators = [
                ("transform", self.validate_set_transform, False),
                ("extra_tags", self.validate_string_list, False),
        ]

        self.tag_defaults = {}

    def reset(self):
        allfeeds.reset()
        alltags.reset()

        self.errors = {}
        self.final = {}

        # Accumulators for verifying uniqueness
        self.urls = []
        self.feed_names = []

    def parse(self, fromfile=True, changes={}):
        parse_locks()

        # Since we host client config too, check if
        # we should do a reparse.

        we_care = False
        for header in [ "feeds", "tags", "defaults" ]:
            if header in changes:
                if header == "tags":
                    for tag in changes["tags"]:
                        if list(changes["tags"][tag].keys()) != [ "collapsed" ]:
                            we_care = True
                    if we_care:
                        break
                else:
                    we_care = True
                    break

        if fromfile or we_care:
            self.reset()
            if fromfile:
                self.read_config()
            if self.validate():
                self.instantiate()
                if not fromfile:
                    self.write()
        elif not fromfile:
            self.write()

        parse_unlocks()

    def read_config(self):
        if not os.path.exists(self.filename):
            log.info("No config found, writing default.")
            self.json = default_config.copy()
            self.write()

        c = codecs.open(self.filename, "rb", locale_enc)
        self.json = json.load(c)
        c.close()

        log.info("Read %s" % self.filename)
        log.debug("Parsed into: %s", self.json)

    def error(self, ident, val, error):
        if ident in self.errors:
            self.errors[ident].append((val, error))
        else:
            self.errors[ident] = [(val, error)]

    def _validate_unique(self, ident, value, accumulator, desc):
        if not self.validate_string(ident, value):
            return False

        if value in accumulator:
            self.error(ident, value, "%s already used!" % (desc,))
            return False

        accumulator.append(value)
        return (True, value)

    def validate_unique_url(self, ident, value):
        return self._validate_unique(ident, value, self.urls, "URL")

    def validate_unique_feed_name(self, ident, value):
        return self._validate_unique(ident, value, self.feed_names, "Feed name")

    def validate_bool(self, ident, value):
        if type(value) != bool:
            self.error(ident, value, "Not boolean!")
            return False
        return (True, value)

    def validate_int(self, ident, value):
        if type(value) != int:
            self.error(ident, value, "Not integer!")
            return False
        return (True, value)

    def validate_string(self, ident, value):
        if type(value) != str:
            self.error(ident, value, "Not unicode!")
            return False
        return (True, value)

    def validate_string_list(self, ident, value):
        if type(value) != list:
            self.error(ident, value, "Not list!")
            return False

        for idx, item in enumerate(value):
            item_ident = ident + ("[%d]" % idx)
            if not self.validate_string(item_ident, item):
                return False

        return (True, value)

    # Unfortunately, this must return the value, so that the JSON doesn't get
    # tainted with non-serializable values.

    def validate_set_transform(self, ident, value):
        try:
            r = eval_transform(value)
        except Exception as e:
            tb = traceback.format_exc()
            msg = "\n" + "".join(tb)
            self.error(ident, value, "Invalid transform" + msg)
            return (True, "None")

        return (True, value)

    def validate_dict(self, ident_prefix, d, validators):
        section_invalidated = False
        for rgx, validator, required in validators:
            r = re.compile(rgx)

            found = False

            for opt in list(d.keys()):
                match = r.match(opt)
                if not match:
                    continue

                found = True
                ident = ident_prefix + ("[%s]" % opt)

                ret = validator(ident, d[opt])
                if not ret:
                    if required:
                        self.error(ident, d[opt],\
                                "Set but invalid and required!")
                        section_invalidated = True
                    else:
                        self.error(ident, d[opt], "Set but invalid!")
                        del d[opt]
                else:
                    # NOTE: we're ignoring the first tuple, it should
                    # always be True. If it wasn't for the fact that (val,)
                    # looks terrible that could also be returned from the
                    # validators.

                    d[opt] = ret[1]

            if not found and required:
                ident = ident_prefix + "[%s]" % rgx
                self.error(ident, None,\
                        "No matching value found on required option!")
                section_invalidated = True

            if section_invalidated:
                break

        return not section_invalidated

    # Validate validates only what exists in self.final, it does not make
    # substitutions for defaults. That's done on instantiation.

    def validate(self):
        # Because we have to ensure that all items in the JSON are
        # simple, we can do this cheap deepcopy intead of importing
        # copy or doing it ourselves.

        self.final = eval(repr(self.json), {}, {})

        if "defaults" in self.final:
            good = self.validate_dict("[defaults]", self.final["defaults"],
                    self.defaults_validators)
            if not good:
                del self.final["defaults"]

        if "tags" in self.final and not self.errors:
            for tag in list(self.final["tags"].keys()):
                good = self.validate_dict("[tags][" + tag + "]", self.final["tags"][tag],
                        self.tag_validators)
                if not good:
                    del self.final["tags"][tag]

        if "feeds" in self.final and not self.errors:
            for i, feed in enumerate(self.final["feeds"][:]):
                good = self.validate_dict("[feeds][%s]" % i, feed,
                        self.feed_validators)
                if not good:
                    self.final["feeds"].remove(feed)

        if self.errors:
            log.error("ERRORS:")
            for key in list(self.errors.keys()):
                log.error("%s:" % key)
                for value, error in self.errors[key]:
                    log.error("\t%s -> %s" % (value, error))
            return False

        log.info("Validated: %s" % self.final)
        return True

    # Create Tag and Feed objects based on final validated config

    def instantiate(self):

        if "defaults" in self.final:
            for k in self.defaults_defaults.keys():
                if k not in self.final["defaults"]:
                    self.final["defaults"][k] = self.defaults_defaults[k]
        else:
            self.final["defaults"] = self.defaults_defaults.copy()

        if "tags" in self.final:
            for tag in self.final["tags"]:
                defs = self.final["tags"][tag]

                if "transform" not in defs:
                    defs["transform"] = "None"

                defs["transform"] = eval_transform(defs["transform"])

                if "extra_tags" not in defs:
                    defs["extra_tags"] = []

                alltags.tag_transform(tag, defs["transform"])
                alltags.set_extra_tags(tag, defs["extra_tags"])

        # Feeds must be instantiated *after* tags, so tag settings like extra_tags
        # can rely on getting an add_tag for each item after all tag settings have
        # been handled.

        if "feeds" in self.final:
            for feed in self.final["feeds"]:

                # Mandatory arguments to CantoFeed
                for k in [ "rate", "keep_time", "keep_unread" ]:
                    if k not in feed:
                        feed[k] = self.final["defaults"][k]

                # Optional arguments in kwargs
                kws = {}
                for k in ["password", "username"]:
                    if k in feed:
                        kws[k] = feed[k]

                feed = CantoFeed(self.shelf, feed["name"],\
                        feed["url"], feed["rate"], feed["keep_time"], feed["keep_unread"], **kws)

        # Set global transform.

        self.global_transform = eval_transform(\
                self.final["defaults"]["global_transform"])

    # Delete settings from the JSON. Any key equal to "DELETE" will be removed,
    # keys that are lists will items removed if specified.

    def _delete(self, deletions, current):
        for key in list(deletions.keys()):

            # Nothing to do.

            if key not in current:
                continue

            # Delete surface fields.

            if deletions[key] == "DELETE":
                del current[key]

            # Delete potential fields in deeper dicts.

            elif type(deletions[key]) == dict:
                self._delete(deletions[key], current[key])

            # If we've specified a list for and are operating on a list,
            # then eliminate those.

            elif type(deletions[key]) == list and\
                    type(current[key]) == list:

                log.debug("Deleting items from list lists:")
                log.debug("\\%s", deletions[key])
                log.debug("\\%s", current[key])

                for item in deletions[key]:
                    if item in current[key]:
                        current[key].remove(item)

    def delete(self, deletions):
        self._delete(deletions, self.json)

    def _merge(self, change, current):
        for key in list(change.keys()):
            # Move over missing keys

            if key not in current:
                current[key] = change[key]

            # Merge subsequent dicts, or overwrite if wrong types
            # (in a well-behaved merge that shouldn't happen)

            elif type(change[key]) == dict:
                if type(current[key]) != dict:
                    log.warn("Type change! Old value of ['%s'] not dict." %
                            (key,))
                    current[key] = change[key]
                else:
                    self._merge(change[key], current[key])

            # Merge lists (append change items not present in current and
            # potentially change their order based on the contents in change).

            elif type(change[key]) == list:
                if type(current[key]) != list:
                    log.warn("Type change! Old value of ['%s'] not list." %
                            (key, ))
                    current[key] = change[key]
                else:
                    log.debug("Merging lists:")
                    log.debug("\\%s", change[key])
                    log.debug("\\%s", current[key])

                    # Any items not in change are prepended.  This allows the
                    # simple n-item append to work as expected, it allows the
                    # sort case to work as expected, and gives consistent
                    # behavior in the case of items unaccounted for in change.

                    current[key] = [ i for i in current[key] if i not in change[key] ] +\
                            change[key]

            # Move over present

            else:
                current[key] = change[key]

    def merge(self, newconfigs):
        self._merge(newconfigs, self.json)

    def write(self):
        try:
            f = codecs.open(self.filename, "wb", locale_enc)
            json.dump(self.json, f, ensure_ascii=False, sort_keys=True, indent=4)
        finally:
            f.close()

config = CantoConfig()
