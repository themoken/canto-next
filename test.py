#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import tests.encoding
import tests.fetch
import tests.storage
import tests.config
import tests.format
import tests.protocol
import tests.comm
import tests.backend
import tests.feed
import tests.tag
import logging
import unittest
import sys

logging.basicConfig(
    filemode = "w",
    format = "%(asctime)s : %(name)s -> %(message)s",
    datefmt = "%H:%M:%S",
    level = logging.DEBUG
)

all_modules = {
        "encoding" : tests.encoding.Tests,
        "fetch" : tests.fetch.Tests,
        "storage" : tests.storage.Tests,
        "config" : tests.config.Tests,
        "format" : tests.format.Tests,
        "protocol" : tests.protocol.Tests,
        "comm" : tests.comm.Tests,
        "backend" : tests.backend.Tests,
        "feed" : tests.feed.Tests,
        "tag" : tests.tag.Tests }

all_tests = {
        "test_defaults" : tests.encoding.Tests,
        "test_set_encoding" : tests.encoding.Tests,
        "test_good_fetch" : tests.fetch.Tests,
        "test_bad_fetch" : tests.fetch.Tests,
        "test_rate" : tests.fetch.Tests,
        "test_basic_storage" : tests.storage.Tests,
        "test_good_basic" : tests.config.Tests,
        "test_bad_basic" : tests.config.Tests,
        "test_basic_substitution" : tests.format.Tests,
        "test_escape" : tests.format.Tests,
        "test_unmapped_escape" : tests.format.Tests,
        "test_missing_mapping" : tests.format.Tests,
        "test_socket_creation" : tests.protocol.Tests,
        "test_parser" : tests.protocol.Tests,
        "test_communication" : tests.comm.Tests,
        "test_args" : tests.backend.Tests,
        "test_perms" : tests.backend.Tests,
        "test_pid_lock" : tests.backend.Tests,
        "test_list_feeds" : tests.backend.Tests,
        "test_items" : tests.backend.Tests,
        "test_first_update" : tests.feed.Tests,
        "test_attribute_passthru" : tests.feed.Tests,
        "test_id_hierarchy" : tests.feed.Tests,
        "test_unique_id" : tests.feed.Tests,
        "test_clear_tags" : tests.feed.Tests,
        "test_add_tag" : tests.tag.Tests,
        "test_get_tag" : tests.tag.Tests,
        "test_remove_id" : tests.tag.Tests }


if __name__ == "__main__":
    t = []
    if len(sys.argv) == 1:
        for key in all_tests:
            t.append(all_tests[key](key))
    else:
        for arg in sys.argv[1:]:
            if arg in all_tests:
                t.append(all_tests[arg](arg))
            elif arg in all_modules:
                for k in all_tests:
                    if all_tests[k] == all_modules[arg]:
                        t.append(all_tests[k](k))
            else:
                print "Unknown arg: %s" % arg

    suite = unittest.TestSuite()
    suite.addTests(t)
    unittest.TextTestRunner(verbosity=2).run(suite)
