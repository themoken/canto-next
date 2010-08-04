# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from filter import CantoPersistentFilter, CantoSimpleFilter
from feed import CantoFeed
from encoding import decoder

import ConfigParser
import logging
import locale
import os

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

        # For user notification
        self.errors = False

        # Config Sections that aren't feeds
        self.special_sections = ["defaults"]

        # Config's feed objects (non-special sections)
        self.feeds = []

        self.default_rate = 5
        self.default_keep = 0
        self.global_filter = None

    def set(self, section, option, value):
        log.debug("setting %s.%s = %s" % (section, option, value))
        return self.cfg.set(section, option, value.replace("%","%%"))

    def get_section(self, section):
        r = {}
        if not self.cfg.has_section(section):
            return r

        for opt in self.cfg.options(section):
            r[opt] = self.get("", section, opt, None, 0)
        return r

    def get(self, otype, section, option, default, required = 0):
        # Use otype to get the right get_* function
        if hasattr(self.cfg, "get" + otype):
            fn = getattr(self.cfg, "get" + otype)
        else:
            raise Exception

        # Wrap the get_x function in logs
        try:
            r = fn(section, option)
        except ConfigParser.NoSectionError:
            if not required:
                return default
            self.errors = True
            log.info("ERROR: Missing section %s" % section)
            raise
        except ConfigParser.NoOptionError:
            if not required:
                return default
            self.errors = True
            log.info("ERROR: Missing %s in section %s" % (option, section))
            raise
        except ValueError:
            self.errors = True
            log.info("ERROR: Malformed %s in section %s" % (option, section))
            if not required:
                return default
            raise
        except Exception, e:
            self.errors = True
            log.info("Unhandled exception getting %s from section %s: %s" %
                    (option, section, e))
            raise

        if type(r) == str:
            r = decoder(r)

        log.debug("\t%s.%s = %s" % (section, option, r))
        return r

    def parse_feed(self, section):
        name = section[5:]
        log.debug("Found feed: %s" % name)
        try:
            URL = self.get("", section, "URL", "", 1)
        except:
            log.info("ERROR: Missing URL for feed %s" % name)
            return

        rate = self.get("int", section, "rate", self.default_rate)
        keep = self.get("int", section, "keep", self.default_keep)

        # All strings obtained from the config outside of the self.get function
        # must be converted to Unicode. The section name is the only obvious
        # example at this point.

        if type(section) == str:
            section = decoder(section)

        self.feeds.append(CantoFeed(self.shelf, name, URL, rate, keep))

    def parse(self):
        env = { "home" : os.getenv("HOME"),
                "cwd"  : os.getcwd() }

        self.cfg = ConfigParser.SafeConfigParser(env)
        log.debug("New Parser with env: %s" % env)

        if not os.path.exists(self.filename):
            log.debug("No config found, writing default.")
            f = open(self.filename, "w")
            f.write(default_config)
            f.close()

        self.cfg.read(self.filename)
        log.debug("Read %s" % self.filename)
        log.debug("Got sections: %s" % self.cfg.sections())

        if self.cfg.has_section("defaults"):
            log.debug("Parsing defaults:")
            self.default_rate = self.get("int", "defaults", "rate",\
                    self.default_rate)
            self.default_keep = self.get("int", "defaults", "keep",\
                    self.default_keep)

            #XXX: Differentiate between simple and persistent filters.
            gf =  self.get("", "defaults", "global_filter", None)
            if gf:
                t = self.get("","defaults","global_filter_type", "persistent")
                log.debug("T == %s" % t)
                if t == "simple":
                    f = CantoSimpleFilter()
                elif t == "persistent":
                    f = CantoPersistentFilter()

                self.global_filter = f.init(gf)

        # Grab feeds
        for section in self.cfg.sections():
            if section.startswith("Feed "):
                self.parse_feed(section)

    def write(self):
        log.debug("writing config to disk")
        try:
            f = open(self.filename, "wb")
            self.cfg.write(f)
        finally:
            f.close()
