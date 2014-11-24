from canto_next.remote import access_dict

import traceback
import logging
import json

logging.basicConfig(
    format = "%(message)s",
    level = logging.DEBUG
)

import time

class Test(object):
    def __init__(self, name):
        self.name = name
        self.run()

    def compare_flags(self, value):
        if self.flags != value:
            raise Exception("Expected flags %d - got %d" % (value, self.flags))

    def compare_config(self, config, var, evalue):
        ok, got = access_dict(config, var)
        if not ok:
            raise Exception("Couldn't get %s?" % var)
        if got != evalue:
            raise Exception("Expected %s == %s - got %s" % (var, evalue, got))

    def compare_var(self, var, evalue):
        if hasattr(self, var):
            val = getattr(self, var)
            if val != evalue:
                raise Exception("Expected self.%s == %s - got %s" % (var, evalue, val))
        else:
            raise Exception("Couldn't get self.%s?" % var)

    def banner(self, text):
        print("*" * 25)
        print(text)
        print("*" * 25)

    def run(self):
        print("STARTING %s\n" % self.name)

        try:
            r = self.check()
        except Exception as e:
            print("\n%s - FAILED ON EXCEPTION" % self.name)
            print(traceback.format_exc())
            return 1

        if r == True:
            print("\n%s - PASSED\n" % self.name)
            return 0

        print("\n%s - FAILED\n" % self.name)
        return 1

    def check(self):
        pass
