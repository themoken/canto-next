# Canto Reddit Plugin
# by Jack Miller
# v1.2
#
# If this is placed in the plugins directory, it will add a new sort:
# reddit_score_sort, and will add "score [subreddit]" to the beginning of
# every relevant feed item.

# PREPEND_SCORE, if true will add the score to the entry title. Note, this
# doesn't effect the sort.

PREPEND_SCORE = True

# PREPEND_SUBREDDIT, if true will add the [subreddit] to the entry title.

PREPEND_SUBREDDIT = True

# EXTRA_LOG_OUTPUT, if true will log non-error stuff with -v.

EXTRA_LOG_OUTPUT = False

# You shouldn't have to change anything beyond this line.

from canto_next.plugins import check_program

check_program("canto-daemon")

from canto_next.fetch import DaemonFetchThreadPlugin
from canto_next.feed import DaemonFeedPlugin
from canto_next.transform import transform_locals, CantoTransform 

import urllib.request, urllib.error, urllib.parse
import logging
import time
import json
import re

log = logging.getLogger("REDDIT")

def debug(message):
    if EXTRA_LOG_OUTPUT:
        log.debug(message)

keep_attrs = [ "score", "subreddit" ]

class RedditFetchJSON(DaemonFetchThreadPlugin):
    def __init__(self, fetch_thread):
        self.plugin_attrs = {
                "fetch_redditJSON" : self.fetch_redditJSON,
        }

        self.comment_id_regex = re.compile(".*comments/([^/]*)/.*")
        self.tb_id_regex = re.compile(".*tb/([^/]*)")

    def fetch_redditJSON(self, **kwargs):
        if "reddit.com" not in kwargs["feed"].URL:
            return

        # Get the feed's JSON
        try:
            json_url = kwargs["feed"].URL.replace("/.rss","/.json")
            req = urllib.request.Request(json_url, headers = { "User-Agent" : "Canto-Reddit-Plugin"})
            response = urllib.request.urlopen(req, None, 10)
            reddit_json = json.loads(response.read().decode())
        except Exception as e:
            log.error("Error fetching Reddit JSON: %s" % e)
            return

        for entry in kwargs["newcontent"]["entries"]:
            m = self.comment_id_regex.match(entry["link"])
            if not m:
                m = self.tb_id_regex.match(entry["link"])
            if not m:
                debug("Couldn't find ID in %s ?!" % entry["link"])
                continue
            m = "t3_" + m.groups()[0]

            for rj in reddit_json["data"]["children"]:
                if rj["data"]["name"] == m:
                    debug("Found m=%s" % m)

                    d = { "data" : {}}
                    for attr in keep_attrs:
                        if attr in rj["data"]:
                            d["data"][attr] = rj["data"][attr]

                    entry["reddit-json"] = d
                    break
            else:
                debug("Couldn't find m= %s" % m)

class RedditScoreSort(CantoTransform):
    def __init__(self):
        self.name = "Reddit Score Sort"

    def needed_attributes(self, tag):
        return [ "reddit-score" ]

    def transform(self, items, attrs):
        scored = []
        unscored = []

        for item in items:
            if "reddit-score" in attrs[item]:

                # For some reason, reddit-score has been parsed as a string
                # some times. Attempt to coerce.

                if not type(attrs[item]["reddit-score"]) == int:
                    try:
                        attrs[item]["reddit-score"] =\
                                int(attrs[item]["reddit-score"])
                    except:
                        unscored.append(item)
                    else:
                        scored.append(item)
                else:
                    scored.append(item)
            else:
                unscored.append(item)

        scored = [ (attrs[x]["reddit-score"], x) for x in scored ]
        scored.sort()
        scored.reverse()
        scored = [ x for (s, x) in scored ]

        return scored + unscored

class RedditAnnotate(DaemonFeedPlugin):
    def __init__(self, daemon_feed):

        self.plugin_attrs = {
                "edit_reddit" : self.edit_reddit,
        }

    def edit_reddit(self, feed, newcontent, tags_to_add, tags_to_remove, remove_items):
        for entry in newcontent["entries"]:
            if "reddit-json" not in entry:
                debug("NO JSON, bailing")
                continue

            rj = entry["reddit-json"]
            if not rj:
                debug("JSON empty, bailing")
                continue

            if "subreddit" not in entry:
                entry["subreddit"] = rj["data"]["subreddit"]
                if PREPEND_SUBREDDIT:
                    entry["title"] =\
                            "[" + entry["subreddit"] + "] " + entry["title"]

            if PREPEND_SCORE:
                score = rj["data"]["score"]
                if "reddit-score" in entry:
                    entry["title"] = re.sub("^\d+ ", "", entry["title"])

                entry["reddit-score"] = score
                entry["title"] =\
                        ("%d " % entry["reddit-score"]) + entry["title"]

        return (tags_to_add, tags_to_remove, remove_items)

transform_locals["reddit_score_sort"] = RedditScoreSort()
