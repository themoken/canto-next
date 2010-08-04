# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.format import get_formatter
from canto.feed import allfeeds
from canto.encoding import encoder, decoder

from subprocess import Popen, PIPE, call
import traceback
import logging
import shlex

log = logging.getLogger("FILTER")

import os

# The base CantoFilter, gets the basic path and arguments, ensures the path is
# valid and executable.

# CantoFilter init functions return None if there was a problem and `self` if
# there wasn't. So setting a variable like myfilter = CantoFilter("/somepath")
# will either yield a working filter or None as if there was no filter specified
# at all.

class CantoFilter():
    def __str__(self):
        return "Filter: %s" % self.path

    def init(self, path):
        if not path:
            return None

        parsed = shlex.split(encoder(path))
        self.path = decoder(parsed[0])
        self.args = path[len(self.path):]

        self.format_map = {"t" : "title",
                  "s" : "canto-state",
                  "l" : "link",
                  "d" : "description"}

        self.format_attributes = [self.format_map[k] for k in self.format_map]

        if self.ensure_perms() < 0:
            return None

        return self

    def ensure_perms(self):
        if not os.path.exists(self.path):
            log.debug("Filter path %s doesn't exist!" % self.path)
            return -1
        if not os.path.isfile(self.path):
            log.debug("Filter path %s is not a file!" % self.path)
            return -1
        if not os.access(self.path, os.X_OK):
            log.debug("Filter path %s is not executable!" % self.path)
            return -1
        return 0

# A "persistent" filter implementation. The subprocess is forked exactly once
# and is given it's arguments in a set order separated by \0s on STDIN. For each
# set of arguments, it writes "0" or "1" (ASCII) to STDOUT.

# XXX: Eventually this should cleanly timeout on malformed filters, or
# apply_filters could never return.

class CantoPersistentFilter(CantoFilter):
    def init(self, path):
        r = CantoFilter.init(self, path)
        if not r:
            return r

        self.args = self.args.lstrip()
        self.args = self.args.replace(" ", "\0") + "\0"

        self.formatter = get_formatter(self.args, self.format_map)

        self.process = Popen(self.path, stdin=PIPE, stdout=PIPE)

        return self

    def __call__(self, tag):
        res = []
        for i in tag:
            f = allfeeds[i[0]]
            d = f.get_attributes(i, self.format_attributes)

            format_line = self.formatter(d)
            self.process.stdin.write(format_line)

        message = self.process.stdout.read(len(tag))
        for i, c in enumerate(message):
            if c == "1":
                res.append(tag[i])

        return res

# A "simple" filter implementation. This is sort of naive in that the binary is
# forked *for every single item*. It's rather lacking in performance, but since
# (outside of the client init sequence) filtering is done transparently in the
# background, it's okay for extremely simple filters implemented in a language
# that doesn't handle reading / writing well, but arguments are trivial (i.e.
# Bash).

class CantoSimpleFilter(CantoFilter):
    def init (self, path):
        r = CantoFilter.init(self, path)
        if not r:
            return r

        self.formatter = get_formatter(self.args, self.format_map)
        return self

    def __call__(self, tag):
        res = []
        for i in tag:
            f = allfeeds[i[0]]
            d = f.get_attributes(i, self.format_attributes)

            command_line = self.formatter(d)
            full = self.path + " " + command_line

            if call(shlex.split(encoder(full))) == 1:
                res.append(i)
        return res
