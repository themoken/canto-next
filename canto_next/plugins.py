# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import traceback
import logging
import sys
import os

log = logging.getLogger("PLUGINS")

def try_plugins(topdir):
    p = topdir + "/plugins"
    pinit = p + "/__init__.py"

    if not os.path.exists(p):
        log.info("Creating plugins directory.")
        try:
            os.mkdir(p)
        except Exception, e:
            tb = traceback.format_exc(e)
            log.error("Exception creating plugin directory")
            log.error("\n" + "".join(tb))
            return
    elif not os.path.isdir(p):
        log.warn("Plugins file is not directory.")
        return

    if not os.path.exists(pinit):
        log.info("Creating plugin __init__.py")
        try:
            f = open(pinit, "w")
            f.close()
        except Exception, e:
            tb = traceback.format_exc(e)
            log.error("Exception creating plugin __init__.py")
            log.error("\n" + "".join(tb))
            return

    # Add plugin path to front of Python path.
    sys.path.insert(0, topdir)

    # Go ahead and import all .py
    for fname in os.listdir(p):
        if fname.endswith(".py") and fname != "__init__.py":
            try:
                proper = fname[:-3]
                log.info("[plugin] %s" % proper)
                __import__("plugins." + proper)
            except Exception, e:
                tb = traceback.format_exc(e)
                log.error("Exception importing file %s" % fname)
                log.error("\n" + "".join(tb))
