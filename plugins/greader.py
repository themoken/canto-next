# Google Reader Sync Plugin
# by Jack Miller
# v0.2
#
# If this is placed in the .canto-ng/plugins directory, along with a copy of
# the libgreader source ported to py3k and you set the USERNAME and PASSWORD
# settings below, then the read status of your items will be mirrored between
# your Google Reader account and canto.
#
# You can find my basic port of libgreader to py3k here:
# http://codezen.org/static/libgreader-py3k.tar.gz
#
# It only includes the source and should be untarred directly into the plugins
# directory (so plugins/libgreader/ has .py files in it).
#
# CAVEATS
#
# This is a constructive plugin, which means that if you have a different set
# of feeds on your reader account and canto, this plugin will add feeds in both
# places until they're identical. It also will not set items on the reader
# servers as unread if they're already read, which gives proper behavior on
# start up, but may not be proper if you set items unread from the interface.
#
# In addition, this sync adds quite a bit of time to the daemon startup, so it
# would be wise to start canto-daemon separately or canto-curses will complain
# about the daemon not taking a connection fast enough.
#
# TODO
# - Speed

USERNAME="user@gmail.com"
PASSWORD="password"

# You shouldn't have to change anything beyond this line.

from canto_next.feed import DaemonFeedPlugin, allfeeds
from canto_next.hooks import call_hook, on_hook
from plugins.libgreader import GoogleReader, ClientAuthMethod

from threading import Lock
import traceback
import subprocess
import logging
import sys

log = logging.getLogger("GREADER")

def sync_subscriptions():
    log.info("Syncing subscriptions with Google")

    auth = ClientAuthMethod(USERNAME, PASSWORD)
    reader = GoogleReader(auth)
    reader.buildSubscriptionList()

    gurls = [ (f.title, f.feedUrl) for f in reader.getSubscriptionList() ]
    curls = [ f.URL for f in allfeeds.get_feeds() ]
    names = [ f.name for f in allfeeds.get_feeds() ]

    new_feeds = []
    for gtitle, gurl in gurls[:]:
        if gurl not in curls:

            # Handle name collisions because we're not prepared to handle ERROR
            # responses from config

            if gtitle in names:
                offset = 2
                while (gtitle + " (%d)" % offset) in names:
                    offset += 1
                gtitle = gtitle + " (%d)" % offset

            attrs = { "url" : gurl, "name" : gtitle }
            new_feeds.append(attrs)
            names.append(gtitle)

    call_hook("set_configs", [ None, { "feeds" : new_feeds }])

    for curl in curls[:]:
        if curl not in gurls:
            reader.subscribe('feed/' + curl)

on_hook("serving", sync_subscriptions)

auth = ClientAuthMethod(USERNAME, PASSWORD)

reader_lock = Lock()
reader = GoogleReader(auth)

def lock_reader(fn):
    def lock_wrap(*args, **kwargs):
        reader_lock.acquire()
        try:
            r = fn(*args, **kwargs)
        except:
            log.error("FAILURE")
            log.error(traceback.format_exc())
        reader_lock.release()
        return r
    return lock_wrap

class GoogleReaderSync(DaemonFeedPlugin):
    @lock_reader
    def __init__(self):

        self.plugin_attrs = {
                "set_attributes_google" : self.sync_to_google,
                "edit_google" : self.sync_google
        }

        self.g_feed = None

    def _load_items(self, max_items):
        self.g_feed.loadItems()
        old_num = 0
        new_num = self.g_feed.countItems()

        while new_num < max_items and new_num != old_num:
            self.g_feed.loadMoreItems()
            old_num = new_num
            new_num = self.g_feed.countItems()

    def _get_gitem(self, item_content):
        for i in self.g_feed.getItems():
            if (i.title == item_content["title"]) or\
                (i.url == item_content["link"]) or\
                ("summary" in item_content and item_content["summary"] == i.content):
                log.debug("Found matching Google item @ %s" % i.url)
                return i
        else:
            log.warn("Unable to find matching Google item @ %s" % item_content["id"])

    # Two way sync on item load, so that we keep trying, if
    # the set_attributes call didn't find an item.
    #
    # We're loading the items anyway, so why not?

    @lock_reader
    def sync_google(self, **kwargs):
        feed = kwargs["feed"]
        newcontent = kwargs["newcontent"]

        if not self.g_feed:
            reader.buildSubscriptionList()
            for f in reader.getSubscriptionList():
                if f.feedUrl == feed.URL:
                    log.debug("Found matching Google feed @ %s" % f.feedUrl)
                    self.g_feed = f
                    break
            else:
                log.error("Unable to find Google feed @ %s" % feed.URL)
                return

        self._load_items(len(newcontent["entries"]))

        for item in newcontent["entries"]:
            g_item = self._get_gitem(item)

            if not g_item:
                continue
            if "canto-state" not in item:
                item["canto-state"] = []

            if "read" in item["canto-state"] and not g_item.isRead():
                log.debug("Marking %s as read on Google" % item["id"])
                g_item.markRead()
            elif g_item.isRead() and "read" not in item["canto-state"]:
                log.debug("Marking %s as read from Google" % item["id"])
                item["canto-state"].append("read")

        self.g_feed.clearItems()

    # Sending set attributes to google.

    @lock_reader
    def sync_to_google(self, **kwargs):
        if not self.g_feed:
            return

        feed = kwargs["feed"]
        items = kwargs["items"]
        attributes = kwargs["attributes"]
        content = kwargs["content"]

        self._load_items(len(content["entries"]))

        for item in items:
            # We don't care about any other attributes
            if "canto-state" not in attributes[item]:
                continue

            if "read" not in attributes[item]["canto-state"]:
                continue

            try:
                item_cache, item_idx = feed.lookup_by_id(item)
            except:
                continue

            item_content = content["entries"][item_idx]

            g_item = self._get_gitem(item_content)
            if not g_item:
                continue

            log.debug("Marking %s as read on Google" % item)
            g_item.markRead()

        self.g_feed.clearItems()
