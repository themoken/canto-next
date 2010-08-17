# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging
log = logging.getLogger("HOOK")

hooks = {}

def on_hook(hook, func):
    log.debug("Registering func %s for hook: %s" % (func, hook))
    if hook in hooks:
        hooks[hook].append(func)
    else:
        hooks[hook] = [func]

def call_hook(hook, args):
    log.debug("Calling funcs for hook: %s" % hook)
    if hook in hooks:
        for func in hooks[hook]:
            log.debug("\t%s(%s)" % (func, args))
            func(*args)
    else:
        log.debug("\tNone.")
