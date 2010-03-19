# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from feed import CantoFeed

import ConfigParser
import logging
import locale
import os

log = logging.getLogger("CONFIG")

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

    def get(self, otype, section, option, default, required = 0):
        # Use otype to get the right get_* function
        if hasattr(self.cfg, "get" + otype):
            fn = getattr(self.cfg, "get" + otype)
        else:
            raise Exception

        # Wrap the get_x function in logs
        try:
            r = fn(section, option)
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
        log.debug("\t%s.%s = %s" % (section, option, r))
        return r

    def parse_feed(self, section):
        log.debug("Found feed: %s" % section)
        try:
            URL = self.get("", section, "URL", "", 1)
        except:
            log.info("ERROR: Missing URL for feed %s" % section)
            return

        rate = self.get("int", section, "rate", self.rate)
        keep = self.get("int", section, "keep", self.keep)
        self.feeds.append(CantoFeed(self.shelf, URL, rate, keep))

    def parse(self):
        env = { "home" : os.getenv("HOME"),
                "cwd"  : os.getcwd() }
        self.cfg = ConfigParser.SafeConfigParser(env)
        log.debug("New Parser with env: %s" % env)

        self.cfg.read(self.filename)
        log.debug("Read %s" % self.filename)
        log.debug("Got sections: %s" % self.cfg.sections())

        if self.cfg.has_section("defaults"):
            log.debug("Parsing defaults:")
            self.rate = self.get("int", "defaults", "rate", 5)
            self.keep = self.get("int", "defaults", "keep", 0)
        else:
            self.rate = 5
            self.keep = 0

        for section in self.cfg.sections():
            if section in self.special_sections:
                continue
            self.parse_feed(section)
