# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .feed import wlock_feeds
from .hooks import call_hook

import tempfile
import logging
import shutil
import json
import gzip
import time
import os

log = logging.getLogger("SHELF")

class CantoShelf():
    def __init__(self, filename):
        self.filename = filename

        self.cache = {}

        self.open()

    def check_control_data(self):
        if "control" not in self.cache:
            self.cache["control"] = {}

        for ctrl_field in ["canto-modified","canto-user-modified"]:
            if ctrl_field not in self.cache["control"]:
                self.cache["control"][ctrl_field] = 0

    @wlock_feeds
    def open(self):
        call_hook("daemon_db_open", [self.filename])

        if not os.path.exists(self.filename):
            fp = gzip.open(self.filename, "wt", 9, "UTF-8")
            json.dump(self.cache, fp)
            fp.close()
        else:
            fp = gzip.open(self.filename, "rt", 9, "UTF-8")
            try:
                self.cache = json.load(fp)
            except:
                log.info("Failed to JSON load, old shelf?")
                try:
                    import shelve
                    s = shelve.open(self.filename, "r")
                    for key in s:
                        self.cache[key] = s[key]
                except Exception as e:
                    log.error("Failed to migrate old shelf: %s", e)
                    try:
                        f = open(self.filename)
                        data = f.read()
                        f.close()
                        log.error("BAD DATA: [%s]" % data)
                    except Exception as e:
                        log.error("Couldn't even read data? %s" % e)
                        pass
                    log.error("Carrying on with empty shelf")
                    self.cache = {}
                else:
                    log.info("Migrated old shelf")
            finally:
                fp.close()

        self.check_control_data()

    def __setitem__(self, name, value):
        self.cache[name] = value
        self.update_mod()

    def __getitem__(self, name):
        return self.cache[name]

    def __contains__(self, name):
        return name in self.cache

    def __delitem__(self, name):
        if name in self.cache:
            del self.cache[name]
        self.update_mod()

    def update_umod(self):
        if "control" not in self.cache:
            self.cache["control"] = self.cache['control']

        ts = int(time.mktime(time.gmtime()))
        self.cache["control"]["canto-user-modified"] = ts
        self.cache["control"]["canto-modified"] = ts

    def update_mod(self):
        if "control" not in self.cache:
            self.cache["control"] = self.cache['control']

        ts = int(time.mktime(time.gmtime()))
        self.cache["control"]["canto-modified"] = ts

    @wlock_feeds
    def sync(self):

        # If we get a sync after we're closed, or before we're open
        # just ignore it.

        if self.cache == {}:
            return

        f, tmpname = tempfile.mkstemp("", "feeds", os.path.dirname(self.filename))
        os.close(f)

        fp = gzip.open(tmpname, "wt", 9, "UTF-8")
        json.dump(self.cache, fp, indent=4, sort_keys=True)
        fp.close()

        log.debug("Written tempfile.")

        shutil.move(tmpname, self.filename)

        log.debug("Synced.")

    def close(self):
        log.debug("Closing.")
        self.sync()
        self.cache = {}
        call_hook("daemon_db_close", [self.filename])
