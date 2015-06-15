# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2014 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import traceback
import logging

log = logging.getLogger("HOOKS")

hooks = {}

def on_hook(hook, func, key=None):
    if key and type(key) != str:
        key = str(key)

    if hook in hooks:
        hooks[hook].append((key, func))
    else:
        hooks[hook] = [(key, func)]

def _trim_hooks():
    for key in list(hooks.keys()):
        if hooks[key] == []:
            del hooks[key]

def remove_hook(hook, func):
    hooks[hook] = [ x for x in hooks[hook] if x[1] != func ]
    _trim_hooks()

def unhook_all(key):
    if key and type(key) != str:
        key = str(key)
    for hook in hooks:
        hooks[hook] = [ x for x in hooks[hook] if x[0] != key ]
    _trim_hooks()

def call_hook(hook, args):
    if hook in hooks:
        # List copy here so hooks can remove themselves
        # without effecting our iteration.

        try:
            for key, func in hooks[hook][:]:
                func(*args)
        except:
            log.error("Error calling hook %s (func: %s args: %s)" % (hook, func, args))
            log.error(traceback.format_exc())
