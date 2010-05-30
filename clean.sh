#!/bin/sh

sudo rm -rf build
find -name "*.pyc" | xargs rm -v
