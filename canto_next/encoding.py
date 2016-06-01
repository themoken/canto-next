# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import locale

locale_enc = locale.getpreferredencoding()

# These are basically just wrappers to close the encoding
# options into their scopes so we don't have to pass the 
# encoding around or call the above a million times.

def get_encoder(errors = "replace", encoding = None):
    if not encoding:
        encoding = locale_enc

    def encoder(s):
        return s.encode(encoding, errors)
    return encoder

encoder = get_encoder()
