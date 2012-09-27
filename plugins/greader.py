# Google Reader Sync Plugin
# by Jack Miller
# v1.0
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
#
# - Get subscription synchronization working (infra works when run outside of
# plugin interface, haven't quite gotten the internal implementation right.
# - Should probably stop using canto-remote
# - Speed

USERNAME="user@gmail.com"
PASSWORD="password"

# You shouldn't have to change anything beyond this line.

from canto_next.feed import DaemonFeedPlugin
from canto_next.hooks import on_hook, remove_hook
from plugins.libgreader import GoogleReader, ClientAuthMethod

from threading import Lock
import subprocess
import logging
import sys
import os

log = logging.getLogger("GREADER")

sub_synced = False

def get_reader_urls(reader):
    reader.buildSubscriptionList()
    return [ f.feedUrl for f in reader.getSubscriptionList() ]

def get_canto_urls():
    listfeeds = subprocess.check_output(['canto-remote', 'listfeeds'])
    listfeeds = listfeeds.decode("UTF-8")
    return [ l for l in listfeeds.split('\n') if l.startswith('http') ]

def add_reader_urls(reader, new_urls):
    for url in new_urls:
        log.info("Adding %s to Google Reader" % url)
        r = reader.subscribe("feed/" + url)
        if r:
            log.info("...OK")
        else:
            log.info("...FAILED!")

def add_canto_urls(new_urls):
    for url in new_urls:
        subprocess.check_output(['canto-remote', 'addfeed', url])

def sync_subscriptions():
    log.info("Syncing subscriptions with Google")

    auth = ClientAuthMethod(USERNAME, PASSWORD)
    reader = GoogleReader(auth)

    if os.fork():
        gurls = get_reader_urls(reader)
        curls = get_canto_urls()

        for gurl in gurls[:]:
            if gurl in curls:
                gurls.remove(gurl)

        for curl in curls[:]:
            if curl in gurls:
                curls.remove(curl)

        self.add_reader_urls(reader, curls)
        self.add_canto_urls(gurls)
        sys.exit(0)

    remove_hook("serving", sync_subscriptions)

#on_hook("serving", sync_subscriptions)

auth = ClientAuthMethod(USERNAME, PASSWORD)

reader_lock = Lock()
reader = GoogleReader(auth)

def lock_reader(fn):
    def lock_wrap(*args, **kwargs):
        reader_lock.acquire()
        log.debug("got reader_lock")
        r = fn(*args, **kwargs)
        reader_lock.release()
        log.debug("released reader_lock")
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
