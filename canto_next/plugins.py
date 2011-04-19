# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import traceback
import logging
import inspect
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

arg_transforms = {}
def add_arg_transform(fn, trans):

    # If we get passed a method, get its
    # func implementation.

    if hasattr(fn, "__func__"):
        fn = fn.__func__

    arg_transforms[repr(fn)] = trans

class PluginHandler(object):
    def __init__(self):
        self.plugin_funcs = {}

    def __getattribute__(self, name):
        try:
            objs = [(self, object.__getattribute__(self, name))]
        except AttributeError:
            # Ignore these to avoid recursing forever
            if name in [ "plugin_class", "plugin_class_instances"]:
                raise

            # If we have no plugin class, we really don't have the attribute
            if not hasattr(self, "plugin_class"):
                raise

            # Generate the instance list, if necessary.
            if not hasattr(self, "plugin_class_instances"):
                self.plugin_class_instances = [ c() for c in\
                        self.plugin_class.__subclasses__() ]

            # Check plugin instances for the same attribute.

            objs = []
            for c in self.plugin_class_instances:
                if hasattr(c, name):
                    o = getattr(c, name)

                    # Ignore non-method attributes. We don't want
                    # to worry about collisions between plugin variables.

                    if not inspect.ismethod(o):
                        continue

                    objs.append((c,o))

            if not objs:
                # Didn't find one, really doesn't exist
                raise
        else:
            if not inspect.ismethod(objs[0][1]):
                return objs[0][1]

        # At this point we have created objs, which is a list of tuples
        # (matched class, matched function) that has at least one tuple in
        # it.

        # If we have multiple matches, something is wrong, unless they're
        # hooks (functions that begin withe hook_pre_ / hook_post_ ), which
        # are assumed to return lists by code later in this function.

        if any([ name.startswith(x) for x in ['hook_pre_','hook_post_']]):
            return objs

        if len(objs) > 1:
            log.error("Too many matches for attribute %s!" % name)
            raise AttributeError

        # Okay, now we have a single object to work on, regardless of whether
        # it's from the current class, or from the subclasses.

        origin_obj, o = objs[0][0], objs[0][1]

        # repr on the func gives a unique identifier. We use this to
        # differentiate the functions without being as shallow as using name.

        func = repr(o.__func__)

        # We've done this collection before, go ahead and use the stored value.
        if name in self.plugin_funcs:
            return self.plugin_funcs[func]

        # Now we're going to create a wrapper function that can:
        # - potentially transform the arguments arbitrarily using
        #   arg_transforms.
        # - calls all hook_pre/hook_post functions
        # - calls either the real function or one overriding function
        #
        # We take advantage of the functionality built in above to count on
        # the fact that getting the 'hook_pre_name' and 'hook_post_name'
        # attributes will build and return a list dynamically. Because of the
        # more expensive nature of __getattribute__ we just attempt to get
        # it, instead of calling hasattr first.

        try:
            over = getattr(self, "override_" + name)
        except AttributeError:
            over = o

        try:
            hook_pres = getattr(self, "hook_pre_" + name)
        except AttributeError:
            hook_pres = []

        try:
            hook_posts = getattr(self, "hook_post_" + name)
        except AttributeError:
            hook_posts = []

        if func in arg_transforms:
            argt = arg_transforms[func]
        else:
            argt = None

        # If we're not going to use any of the features, then don't bother
        # wrapping. This keeps out unnecessary resources and needlessly
        # complex backtraces.

        if not argt and not hook_posts and not hook_pres and over == o:
            self.plugin_funcs[func] = o
            return o

        def newfunc(*args, **kwargs):
            if argt:
                r = argt(args[0], origin_obj, *args[1:], **kwargs)
                if not r:
                    return
                args, kwargs = r

            for c, f in hook_pres:
                try:
                    f(*args, **kwargs)
                except Exception, e:
                    tb = traceback.format_exc(e)
                    log.error("Exception running pre hook %s from %s" % (f, c))
                    log.error("\n" + "".join(tb))

            r = over(*args, **kwargs)
            kwargs["ret"] = r

            for c, f in hook_posts:
                try:
                    f(*args, **kwargs)
                except Exception, e:
                    tb = traceback.format_exc(e)
                    log.error("Exception running post hook %s from %s" % (f, c))
                    log.error("\n" + "".join(tb))

            return r

        self.plugin_funcs[func] = newfunc
        return newfunc

# Plugin is the base class for all of the separate plugin classes for each Gui
# object. There are two reasons to pin plugins to an empty class:
#
# - 'object' in the hierarchy via PluginHandler means we can use
#   __subclasses__, the cornerstone of the plugins system
#
# - This allows the plugins to have a hard distinction between self (the
#   instantiated class object) and obj (the instantiated main object that's
#   being overridden). This means that plugins don't have to worry about
#   clobbering anything.
#
# As a side effect, using the separate plugin architecture, we also can
# enable/disable pluggability on a class basis. For example, if TagList
# didn't specify a plugin_class, then it could not be overridden or hooked.

class Plugin(object):
        pass
