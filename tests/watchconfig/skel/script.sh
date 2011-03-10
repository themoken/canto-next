#!/bin/bash

# This test ensures that:
# 1) WATCHCONFIGS works
# 2) WATCHCONFIGS only notifies connections that *didn't* originate the
#   change. This helps keep pointless traffic down on the socket, as well
#   as avoiding any potential config echo if a setting is changed multiple
#   times while processing.
# 3) WATCHCONFIGS only notifies of the latest changes.

echo "
WATCHCONFIGS {}
SETCONFIGS { \"test\" : { \"testopt\" : \"value\" } }
PING {}

# This should show the PONG response, indicating
# that the SETCONFIGS action didn't result in
# any response.
REMOTE_WAIT 1

# Now wait for the second c-r's config notification.
REMOTE_WAIT 1" > script1

canto-remote -D ./ script script1 > out1 &
PID1=$!

# Wait for the first canto-remote to be waiting on the config. If the
# second script is run immediately, it may (and does) execute first
# and its config change ends up being already present. This could probably
# be done a little smarter, but my bash-fu is lacking it.

sleep 2

echo "SETCONFIGS { \"test\" : { \"testopt2\" : \"othervalue\" } }" > script2

canto-remote -D ./ script script2 > out2

# Wait for the first c-r to finish.
wait $PID1

echo ">>> Remote #1 <<<"
cat out1
echo ""
echo ">>> Remote #2 <<<"
cat out2
