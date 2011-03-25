#!/bin/bash

# This test ensures that canto-daemon will keep 2x the number
# of naturally presented items to prevent item bounce.

mv ./canto.xml /tmp/

canto-remote -D ./ script <<EOF
# The skel/feeds database has items 1. - 5.
# skel/canto.xml contains new items 6. - 9. with no overlap

WATCHTAGS [ "maintag\\\\:Static" ]
UPDATE {}

# Get one tag change.
REMOTE_WAIT 1

# Note that item 5 should be dropped as it's unprotected, and
# doesn't fall in the 2x area of old items.
ITEMS [ "maintag\\\\:Static" ]

REMOTE_WAIT 1
EOF
