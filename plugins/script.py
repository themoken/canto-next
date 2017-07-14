# Canto Script Plugin
# by Jack Miller
# v1.0

# With this plugin you can add a feed with a URL starting with "script:" and
# ending with a simple script invocation. You must specify a name for the feed.
#
# For example:
#   canto-remote addfeed "script:~/bin/feed.sh" name="Script Feed"
#
# Scripts must have executable permissions.
#
# Scripts can be passed constant arguments, but are not executed in a shell
# environment.
#
# The script path should be absolute, or relative to home (~/), relative path
# behavior is undefined.
#
# Scripts are expected to output parsable RSS/Atom XML to stdout.

from canto_next.plugins import check_program

check_program("canto-daemon")

from canto_next.fetch import DaemonFetchThreadPlugin
from canto_next.feed import DaemonFeedPlugin

import feedparser
import subprocess
import logging
import shlex
import os

log = logging.getLogger("SCRIPT")

def debug(message):
    if EXTRA_LOG_OUTPUT:
        log.debug(message)

class ScriptFetch(DaemonFetchThreadPlugin):
    def __init__(self, fetch_thread):
        self.plugin_attrs = {
                "fetch_script" : self.fetch_script,
        }

    def fetch_script(self, **kwargs):
        if not kwargs["feed"].URL.startswith("script:"):
            return

        path = os.path.expanduser(kwargs["feed"].URL[7:])

        log.debug("path: %s", path)

        path = shlex.split(path)

        log.debug("split: %s", path)

        output = subprocess.check_output(path)

        log.debug("output: %s", output)

        contents = kwargs["newcontent"]
        contents.clear()

        feed = feedparser.parse(output)

        for key in feed:
            contents[key] = feed[key]
