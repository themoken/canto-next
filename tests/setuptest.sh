#!/bin/bash

# Setup some directories (clean it up, move in skel/*, start daemon)

for test_dir in "$@"; do
    ./clean.sh $test_dir

    # Copy any premade files from skel into directory.

    cp -r ./$test_dir/skel/* ./$test_dir/

    # Start daemon there.

    canto-daemon -n -v -D "./$test_dir" &

    while [ ! -e "./$test_dir/.canto_socket" ]; do
        sleep 0.1
    done
done
