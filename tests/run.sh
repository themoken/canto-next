#!/bin/bash

# Run specified tests.

for test_dir in "$@"; do
    ./setuptest.sh $test_dir

    cd $test_dir
    ./script.sh > output
    cd ..

    # Compare output to expected output.

    TESTDIFF=`diff -u ./$test_dir/output ./$test_dir/expected`
    if [ -n "$TESTDIFF" ]; then
        echo "TEST $test_dir FAILED"
        diff -u ./$test_dir/output ./$test_dir/expected
    else
        echo "TEST $test_dir OK"
    fi

    # Kill daemon.

    kill -SIGINT `cat ./$test_dir/pid`
done
