#!/bin/sh

sudo rm -rf build
find -name "*.pyc" | xargs rm -v
find -name ".canto_socket" | xargs rm -v
