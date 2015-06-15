#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from base import *

from canto_next.feed import CantoFeed, dict_id, allfeeds
from canto_next.tag import alltags
import time

TEST_URL = "http://example.com/"
DEF_KEEP_TIME = 86400

class TestFeedIndex(Test):

    # Make sure all items in the feeds have all of their tags...

    def compare_feed_and_tags(self, shelf):
        for feed in allfeeds.get_feeds():
            maintag = "maintag:" + feed.name
            for entry in shelf[feed.URL]["entries"]:
                full_id = feed._item_id(entry)
                if maintag not in alltags.items_to_tags([full_id]):
                    raise Exception("Item %s didn't make it into tag %s" % (entry, maintag))

                if "canto-tags" in entry:
                    for tag in entry["canto-tags"]:
                        if tag not in alltags.items_to_tags([full_id]):
                            raise Exception("Item %s didn't make it into user tag %s" % (entry, tag))

        self.compare_tags_and_feeds(shelf)

    # ... and make sure that all tags have a real source in the feeds

    def compare_tags_and_feeds(self, shelf):
        for tag in alltags.get_tags():
            for item in alltags.tags[tag]:
                URL = dict_id(item)["URL"]
                id = dict_id(item)["ID"]

                feed = allfeeds.get_feed(dict_id(item)["URL"])
                if tag.startswith("maintag:") and tag[8:] == feed.name:
                    continue

                for entry in shelf[feed.URL]["entries"]:
                    if id == entry["id"] and tag not in entry["canto-tags"]:
                        raise Exception("Tag %s has no source: %s / %s!" % (tag, feed.name, entry))

    def generate_update_contents(self, num_items, item_content_template, update_time):
        entries = []

        for i in range(num_items):
            c = eval(repr(item_content_template))
            for key in c:
                if type(c[key]) == str and "%d" in c[key]:
                    c[key] = c[key] % i
            entries.append(c)

        return { "canto_update" : update_time,  "entries" : entries }

    # Generate a feed and shelf 

    def generate_baseline(self, feed_name, feed_url, num_items, item_content_template, update_time):
        alltags.reset()
        allfeeds.reset()

        test_shelf = {}
        test_feed = CantoFeed(test_shelf, feed_name, feed_url, 10, DEF_KEEP_TIME, False)
        update = self.generate_update_contents(num_items, item_content_template, time.time())

        test_feed.index(update)

        self.compare_feed_and_tags(test_shelf)

        if "maintag:Test Feed" not in alltags.tags:
            raise Exception("Failed to populate maintag")

        if len(alltags.tags["maintag:Test Feed"]) != 100:
            raise Exception("Failed to put items in maintag")

        if feed_url not in test_shelf:
            raise Exception("Failed to write to shelf")

        if "entries" not in test_shelf[feed_url]:
            raise Exception("Failed to get any entries")

        if len(test_shelf[feed_url]["entries"]) != 100:
            raise Exception("Failed to record all items")

        test_shelf["canto_update"] = update_time

        for i, entry in enumerate(test_shelf[feed_url]["entries"]):
            if "id" not in entry:
                raise Exception("Failed to id item %d" % i)
            if "canto_update" not in entry:
                raise Exception("Failed to record update time on item %d" % i)

            entry["canto_update"] = update_time

        return test_feed, test_shelf, update

    def check(self):
        content = {
                "title" : "Title %d",
                "link" : TEST_URL + "%d/",
        }

        update_content = {
                "title" : "Title %d updated",
                "link" : TEST_URL + "%d/updated",
        }

        self.banner("sanity")

        # Index basic sanity checks (should write to shelf, should populate tags)
        # All internal to the baseline generator.

        f, s, u = self.generate_baseline("Test Feed", "http://example.com", 100, content, time.time())

        self.banner("discard")

        now = time.time()
        test_feed, test_shelf, first_update = self.generate_baseline("Test Feed", TEST_URL, 100, content, now - (DEF_KEEP_TIME + 1))

        second_update = self.generate_update_contents(100, update_content, now)

        # Keep some items from the first update

        second_update["entries"].extend(first_update["entries"][:5])

        test_feed.index(second_update)

        self.compare_feed_and_tags(test_shelf)

        tag = alltags.tags["maintag:Test Feed"]
        nitems = len(tag)

        if nitems != 105:
            raise Exception("Wrong number of items in tag! %d - %s" % (nitems, tag))
        if dict_id(tag[100])["ID"] != "http://example.com/0/":
            raise Exception("Failed to keep order got id = %s" % dict_id(tag[100])["ID"])

        self.banner("keep_time")

        test_feed, test_shelf, first_update = self.generate_baseline("Test Feed", TEST_URL, 100, content, now - 300)

        test_feed.index(second_update)

        self.compare_feed_and_tags(test_shelf)

        tag = alltags.tags["maintag:Test Feed"]
        nitems = len(tag)
        if nitems != 200:
            raise Exception("Wrong number of items in tag! %d - %s" % (nitems, tag))
        if dict_id(tag[0])["ID"] != "http://example.com/0/updated":
            raise Exception("Failed to keep order got id = %s" % dict_id(tag[0])["ID"])
        if dict_id(tag[100])["ID"] != "http://example.com/0/":
            raise Exception("Failed to keep order got id = %s" % dict_id(tag[100])["ID"])
        if dict_id(tag[199])["ID"] != "http://example.com/99/":
            raise Exception("Failed to keep order got id = %s" % dict_id(tag[199])["ID"])

        self.banner("keep_unread")

        now = time.time()
        test_feed, test_shelf, first_update = self.generate_baseline("Test Feed", TEST_URL, 100, content, now - (DEF_KEEP_TIME + 1))

        test_feed.keep_unread = True

        # Mark five that aren't keep_unread protected, but are too young to discard
        for i in range(5):
            test_shelf[TEST_URL]["entries"][i]["canto_update"] = now - 300
            test_shelf[TEST_URL]["entries"][i]["canto-state"] = [ "read" ]

        # Mark 25 that should be discarded
        for i in range(25, 50):
            test_shelf[TEST_URL]["entries"][i]["canto-state"] = [ "read" ]

        second_update = self.generate_update_contents(100, update_content, now)

        test_feed.index(second_update)

        self.compare_feed_and_tags(test_shelf)

        tag = alltags.tags["maintag:Test Feed"]
        nitems = len(tag)

        if nitems != 175:
            raise Exception("Wrong number of items in tag! %d - %s" % (nitems, tag))

        self.banner("save all items on empty new content")

        test_feed, test_shelf, first_update = self.generate_baseline("Test Feed", TEST_URL, 100, content, now - (DEF_KEEP_TIME + 1))

        test_feed.index(self.generate_update_contents(0, update_content, now))

        tag = alltags.tags["maintag:Test Feed"]
        nitems = len(tag)

        if nitems != 100:
            raise Exception("Wrong number of items in tag! %d - %s" % (nitems, tag))

        return True

TestFeedIndex("feed index")
