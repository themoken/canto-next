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

from canto_next.fetch import DaemonFetchThreadPlugin
from canto_next.feed import DaemonFeedPlugin
from canto_next.transform import transform_locals, CantoTransform 

import urllib2
import logging
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

        for entry in kwargs["newcontent"]["entries"]:
            if "reddit-json" in entry:
                continue

            # Grab the story summary. Alternatively, we could grab
            # entry["link"] + "/.json" but that includes comments and
            # can be fairly large for popular threads.

            try:
                m = self.id_regex.match(entry["link"])
                reddit_id = m.groups()[0]

                response = urllib2.urlopen(\
                        "http://reddit.com/by_id/t3_" + reddit_id + ".json")

                r = json.load(response)
                entry["reddit-json"] = r
            except Exception, e:
                log.error("Error fetching Reddit JSON: %s" % e)
                entry["reddit-json"] = {}

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

        scored.sort(lambda x, y :\
                attrs[y]["reddit-score"] - attrs[x]["reddit-score"])

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
            if not json:
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
