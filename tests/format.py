#! -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from canto.format import get_formatter
import logging

log = logging.getLogger("TEST-FORMAT")

keys = { 'a' : "alpha", 'b' : "beta" }
subs = { "alpha" : "Lorem", "beta" : "ipsum" }

def one_test(fmt, expected, extrakeys = {}):
    newkeys = keys.copy()
    newkeys.update(extrakeys)
    f = get_formatter(fmt, newkeys)
    result = f(subs)
    if result != expected:
        log.debug("Wrong Result: %s" % result)
        return 0
    return 1

def test():
    if not one_test("%a - %b", "Lorem - ipsum"):
        log.debug("FAILED basic substitution")
        return
    if not one_test("%a\%%b", "Lorem%ipsum"):
        log.debug("FAILED escape")
        return
    if not one_test("%a %b %c", "Lorem ipsum "):
        log.debug("FAILED unmapped escape")
        return
    if not one_test("%a %b %c", "Lorem ipsum ", { "c" : "test3" }):
        log.debug("FAILED mapping missing")
        return
    print "FORMAT TESTS PASSED"

def cleanup():
    pass
