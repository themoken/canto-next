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

if __name__ == "__main__":
    alltests = [tests.encoding.Tests('test_defaults'),
                tests.encoding.Tests('test_set_encoding'),
                tests.fetch.Tests('test_good_fetch'),
                tests.fetch.Tests('test_bad_fetch'),
                tests.fetch.Tests('test_rate'),
                tests.storage.Tests('test_basic_storage'),
                tests.config.Tests('test_good_basic'),
                tests.config.Tests('test_bad_basic'),
                tests.format.Tests('test_basic_substitution'),
                tests.format.Tests('test_escape'),
                tests.format.Tests('test_unmapped_escape'),
                tests.format.Tests('test_missing_mapping'),
                tests.protocol.Tests('test_socket_creation'),
                tests.protocol.Tests('test_parser'),
                tests.comm.Tests('test_communication'),
                tests.backend.Tests('test_args'),
                tests.backend.Tests('test_perms'),
                tests.backend.Tests('test_pid_lock'),
                tests.backend.Tests('test_list_feeds'),
                tests.backend.Tests('test_items'),
                tests.feed.Tests('test_first_update'),
                tests.feed.Tests('test_attribute_passthru'),
                tests.feed.Tests('test_id_hierarchy'),
                tests.feed.Tests('test_unique_id'),
                tests.feed.Tests('test_clear_tags'),
                tests.tag.Tests('test_add_tag'),
                tests.tag.Tests('test_get_tag'),
                tests.tag.Tests('test_remove_id')]
    suite = unittest.TestSuite()
    suite.addTests(alltests)
    unittest.TextTestRunner(verbosity=2).run(suite)
