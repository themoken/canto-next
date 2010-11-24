# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

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

def escsplit(arg, delim):
    escaped = False
    for i, c in enumerate(arg):
        if escaped:
            escaped = False
        elif c == '\\':
            escaped = True
        elif c == delim:
            return (arg[:i], arg[i + 1:])
    return (arg, '')
