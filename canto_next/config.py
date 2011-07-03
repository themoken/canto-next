# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from encoding import decoder, locale_enc
from transform import eval_transform
from feed import allfeeds, CantoFeed
from format import escsplit
from tag import alltags

import ConfigParser
import traceback
import logging
import locale
import codecs
import os
import re

log = logging.getLogger("CONFIG")

default_config = """\
[Feed Canto]
url = http://codezen.org/static/canto.xml
order = 0

[Feed Slashdot]
url = http://rss.slashdot.org/slashdot/Slashdot
order = 1

[Feed Reddit]
url = http://reddit.com/.rss
order = 2
"""

class CantoConfig():
    def __init__(self, filename, shelf):
        self.filename = filename
        self.shelf = shelf
        self.conf_chars = [ '.', ':', '=' ]

        # Validator list because order is important, things like global
        # transforms need to be evaluated *after* the transforms are defined for
        # example

        self.defaults_validators = [
                ("rate", self.validate_int, False),
                ("keep", self.validate_int, False),
                ("transform.(?P<idx>\d+).(?P<field>(name|func))",
                    self.validate_transforms, False),
                ("global_transform", self.validate_set_transform, False),
        ]

        # Defaults are native values and are *not* validated so that they can be
        # easily substituted even if validation fails on a user provided value.

        # Usually this means that the defaults listed here are in their end for.
        # For eval'd values, like transforms, they will eval'd in the
        # instantiation phase, so they should be strings at defaults.

        self.defaults_defaults = {
                "rate" : 10,
                "keep" : 0,
                "global_transform" : "None",
        }

        self.feed_validators = [
                ("url", self.validate_unique_url, True),
                ("rate", self.validate_int, False),
                ("keep", self.validate_int, False),
                ("order", self.validate_int, False),
                ("username", self.validate_string, False),
                ("password", self.validate_string, False),
                ("tags", self.validate_string_list, False),
        ]

        self.feed_defaults = {}

        self.tag_validators = [
                ("transform", self.validate_set_transform, False),
        ]

        self.tag_defaults = {}

        # Map sections to validator lists

        self.validators = [
                ("defaults", self.defaults_validators, self.defaults_defaults),
                ("Feed .*", self.feed_validators, self.feed_defaults),
                ("Tag .*", self.tag_validators, self.tag_defaults),
        ]

    def escape(self, s):
        for char in self.conf_chars:
            s = s.replace(char, "\\" + char)
        return s

    def unescape(self, s):
        for char in self.conf_chars:
            s = s.replace("\\" + char, char)
        return s

    def reset(self):
        allfeeds.reset()
        alltags.reset()

        self.errors = {}
        self.parsed = {}
        self.validated = {}
        self.final = {}

        self.feeds = []
        self.transforms = []
        self.urls = []

        self.global_transform = None
        self.tag_transforms = {}

    def parse(self, fromfile=True):
        self.reset()
        self.read_config(fromfile)
        self.validate()
        self.instantiate()

    def read_config(self, fromfile):
        env = { "home" : os.getenv("HOME"),
                "cwd" : os.getcwd() }

        if fromfile:
            self.cfgp = ConfigParser.SafeConfigParser(env)

            # Make sure we are case sensitive, especially for things
            # like keybinds where e and E are different things.

            self.cfgp.optionxform = str

            log.debug("New Parser with env: %s" % env)

            if not os.path.exists(self.filename):
                log.info("No config found, writing default.")
                f = open(self.filename, "wb")
                f.write(default_config)
                f.close()

            self.cfgp.readfp(codecs.open(self.filename, "rb", locale_enc))
            log.info("Read %s" % self.filename)

        for section in self.cfgp.sections():
            esection = decoder(self.escape(section))
            self.parsed[esection] = {}

            for option in self.cfgp.options(section):
                # ConfigParser tacks these on to every section and they
                # aren't very interesting unless used in interpolation.

                if option in env:
                    continue

                eoption = decoder(option)
                self.parsed[esection][eoption] =\
                        decoder(self.cfgp.get(section, option))

        log.debug("Parsed into: %s" % self.parsed)

    def error(self, section, option, val, error):
        if section not in self.errors:
            self.errors[section] = {}
        self.errors[section][option] = (val, error)

    def validate_unique_url(self, section, settings):
        for option in settings:
            val, groups = settings[option]
            if val in self.urls:
                self.error(section, option, val, "URL is not unique!")
                continue

            self.validated[section][option] = val
            self.urls.append(val)

    def validate_int(self, section, settings):
        for option in settings:
            val, groups = settings[option]
            try:
                val = int(val)
            except:
                self.error(section, option, val, "Must be integer")
                continue

            self.validated[section][option] = val

    # i.e. no validation since everything we get is a string.
    def validate_string(self, section, settings):
        for option in settings:
            val, groups = settings[option]
            self.validates[section][option] = val

    def validate_string_list(self, section, settings):
        for option in settings:
            val, groups = settings[option]
            l = [ s.strip().lstrip().rstrip() for s in escsplit(val, ",")]
            self.validated[section][option] = l

    def get_transform_by_name(self, name):
        for transform in self.transforms:
            if transform["name"] == name:
                return transform
        return None

    def validate_set_transform(self, section, settings):
        for option in settings:
            val, groups = settings[option]
            r = self.get_transform_by_name(val)
            if r:
                self.validated[section][option] = val
                return

            # Failing find by name, try to compile it on the fly.
            try:
                r = eval_transform(val)
            except Exception, e:
                tb = traceback.format_exc(e)
                msg = "\n" + "".join(tb)
                self.error(section, option, val,
                        "Invalid transform: %s" % msg)
                continue

            self.validated[section][option] = val

    def validate_transforms(self, section, settings):
        transforms = []

        # First, pair up settings by index

        for option in settings:
            val, groups = settings[option]

            # This won't except it's already %d+ from the regex
            idx = int(groups["idx"])

            # Extend list to right length
            if idx >= len(transforms):
                transforms += [ {} ] * ((idx - len(transforms)) + 1)

            transforms[idx][groups["field"]] = val

        # Now, ensure that every transform has a valid function
        # and finalize the validated["transforms"] list.

        for idx, transform in enumerate(transforms):

            # Keep track of initial idx so that we can still reference
            # by config index without having to keep a sparse list.

            transform["idx"] = idx

            # Ensure there's a function specified for this transform
            if "func" not in transform:
                self.error(section, "transform.%d.func" % idx, "",\
                        "Transform %d missing function" % idx)
                continue

            # If no name specified, use the text representation of the function
            if "name" not in transform:
                transform["name"] = transform["func"]

            # Ensure the transform name is unique.
            if self.get_transform_by_name(transform["name"]):
                self.error(section, "transform.%d.name" % idx,
                        transform["name"],
                        "Transform already exists with that name")
                continue

            # Ensure that the function is valid.
            try:
                transform["func"] = eval_transform(transform["func"])
            except Exception, e:
                tb = traceback.format_exc(e)
                msg = "\n" + "".join(tb)
                self.error(section, "transform.%d.func" % idx,
                        transform["func"],
                        "Invalid transform: %s" % msg)
                continue

            self.transforms.append(transform)

    # Take the raw parsed values and validate them. The output (self.validated)
    # resembles the final product as the options are no longer just strings but
    # native types, however it's still an intermediate form as complex objects
    # (Feeds) haven't actually been created with the config'd values.

    def validate(self):
        for section_rgx, validator_list, defaults in self.validators:
            sr = re.compile(section_rgx)

            for section in self.parsed.keys():
                smatch = sr.match(section)
                if not smatch:
                    continue

                if section not in self.validated:
                    self.validated[section] = {}

                # Sub in defaults to be overridden.
                for option in defaults:
                    if option not in self.validated[section]:
                        self.validated[section][option] =\
                                defaults[option]

                # Validate all matching settings.
                for rgx, validator, required in validator_list:
                    r = re.compile(rgx)
                    settings = {}
                    found = False

                    for option in self.parsed[section].keys():
                        match = r.match(option)
                        if not match:
                            continue

                        found = True
                        settings[option] = (self.parsed[section][option],\
                                match.groupdict())

                    # Detect unset, required settings.

                    if required and not found:
                        self.error(section, rgx, "", "Must be set")
                    else:
                        validator(section, settings)

                        # Detect invalid, required settings by their absence
                        # from the validated dict after validation.

                        if required:
                            invalid_section = False
                            for s in settings:
                                if s not in self.validated[section]:
                                    del self.validated[section]
                                    invalid_section = True
                                    break
                            if invalid_section:
                                break

        # If there's no defaults section we must create one before
        # feeds start trying to use it.

        if "defaults" not in self.validated:
            self.validated["defaults"] = self.defaults_defaults.copy()

        if self.errors:
            log.error("ERRORS: %s" % self.errors)
        log.info("Validated: %s" % self.validated)

    # This takes the self.validated created by validate() and actually creates
    # the Feeds().

    def instantiate(self):
        ordered_feeds = []
        unordered_feeds = []

        for section in self.validated:
            valsec = self.validated[section]

            # Move over defaults, no instantiation necessary.
            if section == "defaults":
                self.final["defaults"] = valsec

            # Collect arguments to instantiate.
            elif section.startswith("Feed "):
                self.final[section] = valsec
                name = section[5:]

                if "rate" not in valsec:
                    valsec["rate"] = self.validated["defaults"]["rate"]
                if "keep" not in valsec:
                    valsec["keep"] = self.validated["defaults"]["keep"]

                kws = {}
                for k in ["password", "username", "tags"]:
                    if k in valsec:
                        kws[k] = valsec[k]

                feed = CantoFeed(self.shelf, name,\
                        valsec["url"], valsec["rate"],
                        valsec["keep"], **kws)

                if "order" in valsec:
                    if valsec["order"] >= len(ordered_feeds):
                        ordered_feeds += [None] * ((valsec["order"] + 1) -
                                len(ordered_feeds))
                    elif ordered_feeds[valsec["order"]]:
                        log.warn("Two feeds with same order (%d)! Demoting %s" %
                                (valsec["order"], name))
                        unordered_feeds.insert(0, feed)
                        continue
                    ordered_feeds[valsec["order"]] = feed
                else:
                    unordered_feeds.append(feed)

            elif section.startswith("Tag "):
                self.final[section] = valsec

                if "transform" not in valsec:
                    valsec["transform"] = "None"

                self.tag_transforms[section[4:]] =\
                        eval_transform(valsec["transform"])

        # Make order explicit, regardless of whether it was in the first place.
        self.feeds = filter(None, ordered_feeds + unordered_feeds)
        for i, feed in enumerate(self.feeds):
            self.set("Feed " + feed.name, "order", unicode(i))

        # Move over any string-based extra (client) configs
        for section in self.parsed:
            if section not in self.validated:
                self.final[section] = self.parsed[section]

        self.global_transform =\
            eval_transform(self.validated["defaults"]["global_transform"])

    def set(self, section, option, value):
        log.debug("setting %s.%s = %s" % (section, option, value))

        # Unescape from backend
        section = self.unescape(section)

        # Config escape %%
        if type(value) in [unicode, str]:
            value = value.replace("%","%%")

        try:
            if not self.cfgp.has_section(section):
                self.cfgp.add_section(section)
        except ValueError:
            log.error("couldn't create section %s, variable not set!" %\
                    section)
            return
        return self.cfgp.set(section, option, value)

    def get(self, section, option):
        if section not in self.final:
            log.warn("tried to get non-existent section: %s" % section)
            return None
        if option not in self.final[section]:
            log.warn("tried to get non-existent option: %s.%s" %\
                    (section, option))
            return None
        return self.final[section][option]

    def get_section(self, section):
        if section in self.final:
            return self.final[section]
        return {}

    def get_sections(self, sections=None):
        if not sections:
            return self.final

        r = {}
        for section in sections:
            if section in self.final:
                r[section] = self.final[section]
        return r

    def has_section(self, section):
        return section in self.final

    def remove_section(self, section):
        del self.final[section]
        return self.cfgp.remove_section(self.unescape(section))

    def write(self):
        try:
            f = codecs.open(self.filename, "wb", locale_enc)
            self.cfgp.write(f)
        finally:
            f.close()
