#!/bin/bash

# This test ensures that:
# 1) Sorts work. This is probably unnecessary as the filter test
# effectively does the same thing and the concepts are general in
# the code (i.e. sorts = filters = "transforms")

mv ./canto.xml /tmp/

canto-remote -D ./ script <<EOF
WATCHTAGS [ "maintag\\\\:Static"]

# Add feed
SETCONFIGS { "Feed Static" : { "url" : "file:///tmp/canto.xml" } }
UPDATE {}
REMOTE_IGNORE 1

# Get ITEMS, should be all 5
ITEMS [ "maintag\\\\:Static", "maintag\\\\:Static 2" ]
REMOTE_WAIT 1

# Switch the filter.
SETCONFIGS { "defaults" : { "global_transform" : "sort_alphabetical" } }
REMOTE_IGNORE 1

# This should be different because of the filterset.
ITEMS [ "maintag\\\\:Static" ]
REMOTE_WAIT 1
EOF

rm /tmp/canto.xml
