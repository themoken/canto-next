# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging

log = logging.getLogger("PROTECT")

# The Protection class keeps a list of IDs whose information should
# never leave the disk. The primary utility of keeping these items around is
# that clients who have outdated (even by just a minute or so) information can
# count on the fact that all of the data associated with those items is still
# retrievable.

class Protection():
    def __init__(self):
        self.prot = {}

    # Return whether a single item tuple is protected.

    def protected(self, item):
        for key in self.prot.keys():
            if item in self.prot[key]:
                log.debug("item %s is protected." % (item,))
                return True

        log.debug("item %s is not protected." % (item,))
        return False

    # Put a set of items under the protection of key.

    def protect(self, key, items):
        if key in self.prot:
            self.prot[key] += items[:]
        else:
            self.prot[key] = items[:]

    # Unprotect a single item under key.

    def unprotect_one(self, key, item):
        if key in self.prot and item in self.prot[key]:
            self.prot[key].remove(item)

    # Unprotect all items under the protection of key.

    def unprotect(self, key):
        log.debug("unprotecting: %s" % key)
        if key in self.prot:
            del self.prot[key]
        log.debug("prot: %s" % self.prot)

protection = Protection()
