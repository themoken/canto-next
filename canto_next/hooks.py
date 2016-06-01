# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import traceback
import logging

log = logging.getLogger("HOOKS")

hooks = {}

def on_hook(hook, func, key=None):
    if key != None and type(key) != str:
        key = str(key)

    if hook in hooks:
        if key in hooks[hook]:
            hooks[hook][key].append(func)
        else:
            hooks[hook][key] = [ func ]
    else:
        hooks[hook] = { key : [ func ] }

def remove_hook(hook, func):
    for key in list(hooks[hook].keys()):
        while func in hooks[hook][key]:
            hooks[hook][key].remove(func)
        if hooks[hook][key] == []:
            del hooks[hook][key]
            if hooks[hook] == {}:
                del hooks[hook]

def unhook_all(key):
    if key != None and type(key) != str:
        key = str(key)
    for hook in list(hooks.keys()):
        if key in hooks[hook]:
            del hooks[hook][key]
            if hooks[hook] == {}:
                del hooks[hook]

def call_hook(hook, args):
    if hook in hooks:
        for key in list(hooks[hook].keys()):
            try:
                for func in hooks[hook][key][:]:
                    try:
                        func(*args)
                    except:
                        log.error("Error calling hook %s (func: %s args: %s)" % (hook, func, args))
                        log.error(traceback.format_exc())
            except:
                pass
