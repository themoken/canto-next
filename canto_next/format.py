# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging

log = logging.getLogger("FORMAT")

def get_formatter(fmt, keys):
    l = len(fmt)
    def formatter(dct):
        s = ""
        i = 0
        while i < l:
            if fmt[i] == '%':
                i += 1
                code = fmt[i]
                if code not in keys:
                    i += 1
                    continue
                key = keys[code]
                if key not in dct:
                    i += 1
                    continue
                s += repr(dct[key])
            elif fmt[i] == '\\':
                s += fmt[i + 1]
                i += 1
            else:
                s += fmt[i]
            i += 1
        return s
    return formatter

def escsplit(arg, delim, maxsplit=0, minsplit=0):
    r = []
    acc = ""
    escaped = False

    for i, c in enumerate(arg):
        if escaped:
            escaped = False
            acc += c

        # We append the escape character because we just want to intelligently
        # split, not unescape the components

        elif c == '\\':
            escaped = True
            acc += c
        elif c == delim:
            r.append(acc)
            acc = ""

            # Last split?
            if maxsplit == 1:
                r.append(arg[i + 1:])
                break
            elif maxsplit > 1:
                maxsplit -= 1
        else:
            acc += c
    else:
        # Get last frag, if we didn't maxout.
        r.append(acc)

    if minsplit > 0 and len(r) < (minsplit + 1):
        r += [ None ] * ((minsplit + 1) - len(r))

    return r

conf_chars = [ '.', ':', '=' ]

def conf_escape(s):
    for char in conf_chars:
        s = s.replace(char, "\\" + char)
    return s

def conf_unescape(s):
    for char in conf_chars:
        s = s.replace("\\" + char, char)
    return s
