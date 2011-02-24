#!/bin/bash

# This test ensures that canto-daemon will keep 2x the number
# of naturally presented items to prevent item bounce.

mv ./canto.xml /tmp/

canto-remote -D ./ script <<EOF
# The skel/feeds database has items 1. - 4.
WATCHTAGS [ "Static" ]
UPDATE {}

# 4 Tag Changes ... 3 new items and 1 lost item
REMOTE_WAIT 4

# Note that item 4 should be dropped as it's unprotected, and
# doesn't fall in the 2x area of old items.
ITEMS [ "Static" ]

REMOTE_WAIT 1
EOF
