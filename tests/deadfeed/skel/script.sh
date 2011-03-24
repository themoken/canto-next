#!/bin/bash

# This test ensures that:
# 1) ITEMS that are committed to clients remain available
#   even after their corresponding feed is removed.
# 2) After a feed is removed, it is no longer advertised in
#   LISTFEEDS, even if it has committed items.
# 3) After the socket(s) that the ITEMS were committed to dies,
#   The items are no longer accessible, even if addressed blindly.

mv ./canto.xml /tmp/

canto-remote -D ./ script <<EOF
WATCHDELTAGS []
WATCHTAGS [ "maintag\\\\:Static" ]

# Add feed
SETCONFIGS { "Feed Static" : { "url" : "file:///tmp/canto.xml" } }
UPDATE {}
REMOTE_WAIT 5

# Get ITEMS so that the daemon will consider them protected.
ITEMS [ "maintag\\\\:Static" ]
REMOTE_WAIT 1

# Remove the feed.
SETCONFIGS { "Feed Static" : None }
REMOTE_WAIT 2

# This should still work, because they're committed.
ATTRIBUTES { (u'file:///tmp/canto.xml', u'http://codezen.org/canto/news/94') : [ "title" ] }
REMOTE_WAIT 1

# However this shouldn't have the "maintag\\\\:Static" tag
LISTTAGS []
REMOTE_WAIT 1
EOF

canto-remote -D ./ script <<EOF
# This should no longer work because the items should've been eliminated.
ATTRIBUTES { (u'file:///tmp/canto.xml', u'http://codezen.org/canto/news/94') : [ "title" ] }
REMOTE_WAIT 1
EOF
