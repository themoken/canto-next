#!/bin/bash

# This test ensures that:
# 1) You get a TAGCHANGE on new items
# 2) You get a TAGCHANGE on filtered representation change
# 3) You get a TAGCHANGE on removed items

mv ./canto-short.xml /tmp/
mv ./canto-long.xml /tmp/

canto-remote -D ./ script <<EOF
WATCHTAGS [ "maintag\\\\:Static" ]

# Add feed
SETCONFIGS { "Feed Static" : { "url" : "file:///tmp/canto-short.xml" } }
UPDATE {}

# One TAGCHANGE for added items
REMOTE_WAIT 1

ITEMS [ "maintag\\\\:Static" ]
REMOTE_WAIT 1

# Switch the filter.
SETCONFIGS { "defaults" : { "global_transform" : "filter_read" } }

# One TAGCHANGE from config reset (items removed from tag)
REMOTE_WAIT 1

# Set an item to be filtered by filter_read
SETATTRIBUTES { (u'file:///tmp/canto-short.xml', u'http://codezen.org/canto/news/92') : { "canto-state" : [ "read" ]} }

# Wait on TAGCHANGE from filter.
REMOTE_WAIT 1

# Change URL to longer feed should get TAGCHANGE for adding.
SETCONFIGS { "Feed Static" : { "url" : "file:///tmp/canto-long.xml" }}
UPDATE {}

# Two TAGCHANGES, one from reset (items removed from tag), one from new items.
REMOTE_WAIT 2

ITEMS [ "maintag\\\\:Static" ]
REMOTE_WAIT 1
EOF

rm /tmp/canto*.xml
