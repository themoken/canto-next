#!/bin/bash

# This test ensures that:
# 1) Configuration headers can be freeform and are properly escaped
#    through the protocol.

echo "
WATCHCONFIGS {}

# Check the current config was properly parsed.
CONFIGS {}
REMOTE_WAIT 1

# Check that arguments given from clients are properly unescaped.
REMOTE_WAIT 1" > script1

canto-remote -D ./ script script1 > out1 &
PID1=$!

sleep 2

echo "SETCONFIGS { \"Test\\=\" : { \"opt\" : \"val2\", \"opt2\" : \"val3\" } }"> script2

canto-remote -D ./ script script2 > out2

wait $PID1

echo ">>> Remote #1 <<<"
cat out1
echo ""
echo ">>> Remote #2 <<<"
cat out2
