#!/bin/bash

# Clean test directory.
# Delete everything but the skel files.

for test_dir in "$@"; do
    rm -f ./$test_dir/.canto_socket
    for f in ./$test_dir/*; do
        if [ "$f" != "./$test_dir/skel" ]; then
            rm -rf "$f"
        fi
    done
done
