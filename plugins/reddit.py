# Canto Reddit Plugin
# by Jack Miller
# v1.0
#
# If this is placed in the plugins directory, it will add a new sort:
# reddit_score_sort, and will add "score [subreddit]" to the beginning of
# every relevant feed item.

# PREPEND_SCORE, if true will add the score to the entry title. Note, this
# doesn't effect the sort.

PREPEND_SCORE = True

# PREPEND_SUBREDDIT, if true will add the [subreddit] to the entry title.

PREPEND_SUBREDDIT = True

# You shouldn't have to change anything beyond this line.

from canto_next.fetch import DaemonFetchThreadPlugin
from canto_next.feed import DaemonFeedPlugin
from canto_next.transform import transform_locals, CantoTransform 

import urllib.request, urllib.error, urllib.parse
import logging
import time
import json
import re

log = logging.getLogger("REDDIT")

class RedditFetchJSON(DaemonFetchThreadPlugin):
    def __init__(self):
        self.plugin_attrs = {
                "fetch_redditJSON" : self.fetch_redditJSON,
        }

        self.id_regex = re.compile(".*comments/([^/]*)/.*")

    def fetch_redditJSON(self, **kwargs):
        if "reddit.com" not in kwargs["feed"].URL:
            return

        last_fetch = 0

        # We don't canonicalize these IDs as the daemon does because reddit has
        # the id set already.

        new_ids = [ i["id"] for i in kwargs["newcontent"]["entries"] ]

        old_attrs = kwargs["feed"].get_attributes(new_ids, ["reddit-json"])

        for entry in kwargs["newcontent"]["entries"]:
            if "reddit-json" in entry:
                continue

            if entry["id"] in old_attrs and\
                    "reddit-json" in old_attrs[entry["id"]]:
                entry["reddit-json"] = old_attrs[entry["id"]]["reddit-json"]
            else:
                # Reddit now enforces a maximum of 1 request every 2 seconds.
                # We can afford to play by the rules because this runs in a
                # separate thread.

                period = 2

                cur_time = time.time()
                delta = cur_time - last_fetch
                if delta < period:
                    log.debug("Waiting %s seconds" % (period - delta))
                    time.sleep(period - delta)
                last_fetch = cur_time

                # Grab the story summary. Alternatively, we could grab
                # entry["link"] + "/.json" but that includes comments and
                # can be fairly large for popular threads.

                try:
                    m = self.id_regex.match(entry["link"])
                    reddit_id = m.groups()[0]

                    req = urllib.request.Request(\
                            "http://reddit.com/by_id/t3_" + reddit_id + ".json",
                            headers = { "User-Agent" : "Canto-Reddit-Plugin"})
                    response = urllib.request.urlopen(req)

                    entry["reddit-id"] = reddit_id

                    r = json.loads(response.read().decode())
                    entry["reddit-json"] = r
                except Exception as e:
                    log.error("Error fetching Reddit JSON: %s" % e)

class RedditScoreSort(CantoTransform):
    def __init__(self):
        pass

    def needed_attributes(self, tag):
        return [ "reddit-score" ]

    def transform(self, items, attrs, immune):
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
    def __init__(self):

        self.plugin_attrs = {
                "edit_reddit" : self.edit_reddit,
        }

    def edit_reddit(self, **kwargs):
        for entry in kwargs["newcontent"]["entries"]:
            if "reddit-json" not in entry:
                log.debug("NO JSON, bailing")
                continue

            json = entry["reddit-json"]
            if not json or "error" in json:
                log.debug("JSON EMPTY, bailing")
                continue

            if "subreddit" not in entry:
                log.debug("no subreddit")
                entry["subreddit"] =\
                        json["data"]["children"][0]['data']["subreddit"]
                if PREPEND_SUBREDDIT:
                    entry["title"] =\
                            "[" + entry["subreddit"] + "] " + entry["title"]
            else:
                log.debug("subreddit already set")

            if "reddit-score" not in entry:
                log.debug("no score")
                entry["reddit-score"] =\
                        json["data"]["children"][0]['data']["score"]
                if PREPEND_SCORE:
                    entry["title"] =\
                            ("%d " % entry["reddit-score"]) + entry["title"]
            else:
                log.debug("score already set")

transform_locals["reddit_score_sort"] = RedditScoreSort()
