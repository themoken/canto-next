#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import canto_next.hooks as hooks

from base import *

class TestHooks(Test):
    def __init__(self, name):
        self.test_set = ""
        self.test_args = []
        Test.__init__(self, name)

    def hook_a(self):
        self.test_set += "a"

    def hook_b(self):
        self.test_set += "b"

    def hook_c(self):
        self.test_set += "c"

    def hook_args(self, *args):
        self.test_args = args

    def check(self):
        hooks.on_hook("test", self.hook_a) # No key
        hooks.on_hook("test", self.hook_b, "first_remove")
        hooks.on_hook("test", self.hook_c, "first_remove")
        hooks.on_hook("test2", self.hook_a, "second_remove")

        hooks.call_hook("test", [])

        if self.test_set != "abc":
            raise Exception("Basic hook test failed: %s" % self.test_set)

        self.test_set = ""
        hooks.call_hook("test2", [])

        if self.test_set != "a":
            raise Exception("Basic hook test2 failed: %s" % self.test_set)

        self.test_set = ""
        hooks.unhook_all("first_remove")
        hooks.call_hook("test", [])

        if self.test_set != "a":
            raise Exception("unhook_all failed: %s" % self.test_set)

        self.test_set = ""
        hooks.remove_hook("test", self.hook_a)
        hooks.call_hook("test", [])

        if self.test_set != "":
            raise Exception("remove_hook failed: %s" % self.test_set)

        hooks.call_hook("test2", [])

        if self.test_set != "a":
            raise Exception("improper hook removed: %s" % self.test_set)

        hooks.unhook_all("second_remove")

        if hooks.hooks != {}:
            raise Exception("hooks.hooks should be empty! %s" % hooks.hooks)

        hooks.on_hook("argtest", self.hook_args)

        for args in [ [], ["abc"], [1, 2, 3] ]:
            self.test_args = []
            hooks.call_hook("argtest", args)
            if self.test_args != tuple(args):
                raise Exception("hook arguments failed in %s out %s" % (args, self.test_args)) 

        return True

TestHooks("hooks")
