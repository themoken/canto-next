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

# Since the inception of the work_done hook that's called from the main loop
# (but doesn't usually have a lot of work to do), these hooks are logged at
# level 8, which is sub-debug level. They can be seen if the daemon is run
# with -vv, but most of the time will be extraneous.

def on_hook(hook, func):
    log.log(8, "Registering func %s for hook: %s" % (func, hook))
    if hook in hooks:
        hooks[hook].append(func)
    else:
        hooks[hook] = [func]

def call_hook(hook, args):
    log.log(8, "Calling funcs for hook: %s" % hook)
    if hook in hooks:
        for func in hooks[hook]:
            log.log(8, "\t%s(%s)" % (func, args))
            func(*args)
    else:
        log.log(8, "\tNone.")
