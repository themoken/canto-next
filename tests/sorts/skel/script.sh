#!/bin/bash

# This test ensures that:
# 1) None works as a filter
# 2) You can dynamically change filter and it has effect.
# 3) Config change is persistent.

mv ./canto.xml /tmp/

canto-remote -D ./ script <<EOF
WATCHTAGS [ "Static"]

# Add feed
SETCONFIGS { "Feed Static" : { "url" : "file:///tmp/canto.xml" } }
REMOTE_IGNORE 5

# Get ITEMS, should be all 5
ITEMS [ "Static", "Static 2" ]
REMOTE_WAIT 1

# Switch the filter.
SETCONFIGS { "defaults" : { "global_transform" : "sort_alphabetical" } }
REMOTE_IGNORE 6

# This should be different because of the filterset.
ITEMS [ "Static" ]
REMOTE_WAIT 1
EOF
