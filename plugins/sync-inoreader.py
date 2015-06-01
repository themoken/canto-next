# Canto Inoreader Plugin
# by Jack Miller
# v0.1

# DEPENDENCIES

# This plugin requires the 'requests' module, which can usually be found in
# your distro's package manager as python3-requests (or python-requests on
# Arch).

# IMPORTANT NOTES

# - When this plugin is enabled, canto will synchronize your subscribed feeds
# with Inoreader. If you've been using canto, you should export your feeds
# (canto-remote export > feeds.opml) and import them into Inoreader if you
# don't want to lose your feeds because Inoreader's info is assumed to be more
# correct than ours.
#
# - Feed subscriptions are only synchronized *from Inoreader* on startup, so if
# you add / remove feeds with Inoreader, you will have to restart the daemon to
# pickup the changes. Adding or removing feeds with canto works properly all
# the time.
#
# - You should probably only enable this if you have disabled other sync-*
# plugins (like sync-rsync). They won't break, but having multiple
# synchronization points is pointless.
#
# - As soon as you enable this plugin, you'll get a bunch of duplicate items
# because Inoreader items have different ids and this plugin doesn't bother to
# try and match them up. Don't fret, it's only temporary.
#
# - You must have a standard Inoreader account, not an OAuth (Google/Facebook
# login).

# CONFIGURATION

# Inoreader credentials

EMAIL="somebody@somewhere"
PASSWORD="passw0rd"

# You don't *have* to change these, but the API is rate limited. So if you want
# to avoid rate limit issues, register your own application Preferences ->
# Developer options on the Inoreader site and replace these.

APP_ID="1000001299"
APP_KEY="i0UOUtLQjj2WTre8WA3a9GWt_cgDhpkO"

BASE_URL="https://www.inoreader.com/reader/"

# === You shouldn't have to change anything past this line. ===

from canto_next.fetch import DaemonFetchThreadPlugin
from canto_next.feed import allfeeds
from canto_next.hooks import call_hook, on_hook
from canto_next.config import config

from urllib.parse import urlencode, quote
import traceback
import requests
import logging
import time
import json

log = logging.getLogger("SYNC-INOREADER")

extra_headers = {
        "User-Agent" : "Canto/0.9.0 + http://codezen.org/canto-ng",
        "AppKey" : APP_KEY,
        "AppID" : APP_ID,
}

def ino_get_auth():
    headers = extra_headers.copy()
    headers['Email'] = EMAIL
    headers['Passwd'] = PASSWORD

    r = requests.get("https://www.inoreader.com/accounts/ClientLogin", headers)
    if r.status_code != 200:
        raise Exception("Failed to authorize: [%s] %s" % (r.status_code, r.text))

    for line in r.text.splitlines():
        if line.startswith("Auth="):
            return line[5:]

    raise Exception("Failed to find Auth= in auth response")

authorization = ino_get_auth()

log.debug("authorization: %s" % authorization)

# XXX : Needs to handle errors / reauth

def inoreader_req(path, query = {}):
    headers = extra_headers.copy()
    headers["Authorization"] = "GoogleLogin auth=" + authorization

    r = requests.get(BASE_URL + path, params=query, headers=headers)

    if r.status_code != 200:
        log.debug("STATUS %s" % r.status_code)
        log.debug(r.headers)
        log.debug(r.text)

    return r

def full_ino_tag_suffix(tag):
    if tag in ["read", "starred"]:
        return "/state/com.google/" + tag
    return "/label/" + tag

def full_ino_tag(tag):
    return "user/-" + full_ino_tag_suffix(tag)

def strip_ino_tag(tag):
    tag = tag.split("/", 3)
    if tag[2] == "state":
        return tag[3].split("/", 1)[1]
    return tag[3]

def has_ino_tag(item, tag):
    if "categories" not in item:
        return False

    suff = full_ino_tag_suffix(tag)
    for category in item["categories"]:
        if category.endswith(suff):
            return True
    return False

def inoreader_add_tag(ino_id, tag):
    path = "api/0/edit-tag?a=" + quote(full_ino_tag(tag))
    path += "&i=" + quote(ino_id)
    inoreader_req(path)

def inoreader_remove_tag(ino_id, tag):
    path = "api/0/edit-tag?r=" + quote(full_ino_tag(tag))
    path += "&i=" + quote(ino_id)
    inoreader_req(path)

def inoreader_get_subs():
    return inoreader_req("api/0/subscription/list").json()["subscriptions"]

def inoreader_add_sub(feed_url, title):
    query = {
        "ac" : "subscribe",
        "s" : "feed/" + feed_url,
        "t" : title
    }

    inoreader_req("api/0/subscription/edit", query)

def inoreader_del_sub(feed_url):
    query = {
        "ac" : "unsubscribe",
        "s" : "feed/" + feed_url
    }
    inoreader_req("api/0/subscription/edit", query)

# For inoreader -> canto, we just fetch all of our feed info from inoreader,
# and convert inoreader's "/state/com.google/read" into canto-state read, as
# well as other tags.

# Technically, we could implement this as a "fetch" function for the fetch
# thread, which is how the Reddit plugin grabs extra information, but since
# inoreader provides all of the content, nicely parsed and in one place anyway,
# we might as well use it instead of feedparser.

class CantoFetchInoReader(DaemonFetchThreadPlugin):
    def __init__(self, fetch_thread):
        self.plugin_attrs = { "run" : self.run }
        self.fetch_thread = fetch_thread

    def add_utag(self, item, tag):
        tag = "user:" + tag
        if "canto-tags" not in item:
            item["canto-tags"] = [ tag ]
        elif tag not in item["canto-tags"]:
            item["canto-tags"].append(tag)

    def run(self):
        # Grab these from the parent object

        feed = self.fetch_thread.feed
        fromdisk = self.fetch_thread.fromdisk

        # From standard run(), if we're just loading from disk (i.e. on
        # startup, we don't need to actually fetch an update.

        if fromdisk:
            feed.index({"entries" : [] })
            return

        feed.last_update = time.time()

        stream_id = quote("feed/" + feed.URL, [])

        query = { "n" : 100 }

        # Collect all of the items

        ino_entries = []
        content_path = "api/0/stream/contents/" + stream_id

        try:
            r = inoreader_req(content_path, query).json()
            ino_entries.extend(r["items"])

            while "continuation" in r:
                query["c"] = r["continuation"]
                r = inoreader_req(content_path, query).json()
                ino_entries.extend(r["items"])
        except Exception as e:
            log.debug("EXCEPT: %s" % traceback.format_exc(e))

        for ino_entry in ino_entries:
            # Compatibility with feedparser
            ino_entry["summary"] = ino_entry["summary"]["content"]
            ino_entry["link"] = ino_entry["canonical"][0]["href"]

            for category in ino_entry["categories"]:
                if category.endswith("/state/com.google/read"):
                    ino_entry["canto-state"] = [ "read" ]
                    continue

                cat = category.split("/", 3)
                if len(cat) < 4:
                    log.debug("Weird category? %s" % cat)
                    continue

                if cat[2] == "state":
                    if cat[3] == "com.google/starred":
                        self.add_utag(ino_entry, "starred")
                elif cat[2] == "label":
                    self.add_utag(ino_entry, cat[3])

        update_contents = { "canto_update" : feed.last_update,
                "entries" : ino_entries }

        update_contents = json.loads(json.dumps(update_contents))

        log.debug("Parsed %s" % feed.URL)

        # Allow DaemonFetchThreadPlugins to do any sort of fetch stuff
        # before the thread is marked as complete.

        for attr in list(self.fetch_thread.plugin_attrs.keys()):
            if not attr.startswith("fetch_"):
                continue

            try:
                a = getattr(self.fetch_thread, attr)
                a(feed = feed, newcontent = update_contents)
            except:
                log.error("Error running fetch thread plugin")
                log.error(traceback.format_exc())

        log.debug("Plugins complete.")

        # This handles it's own locking
        feed.index(update_contents)

# For canto -> inoreader, we tap into hooks

def post_setattributes(socket, args):
    for item_id in args.keys():
        dict_id = json.loads(item_id)

        feed = allfeeds.get_feed(dict_id["URL"])
        ino_id = dict_id["ID"]

        # If the item isn't from inoreader, skip it
        if not ino_id.startswith("tag:google.com,2005:reader/item/"):
            continue

        attrs = feed.get_attributes([item_id], { item_id : ["categories", "canto-state", "canto-tags"] })
        attrs = attrs[item_id]

        if "canto-state" in args[item_id]:
            if "read" in args[item_id]["canto-state"]:
                if not has_ino_tag(attrs, "read"):
                    inoreader_add_tag(ino_id, "read")
            else:
                if has_ino_tag(attrs, "read"):
                    inoreader_remove_tag(ino_id, "read")

        if "canto-tags" in args[item_id]:
            for tag in args[item_id]["canto-tags"]:
                tag = tag.split(":", 1)[1] # strip user: or category: prefix
                if not has_ino_tag(attrs, tag):
                    inoreader_add_tag(ino_id, tag)

            for tag in attrs["categories"]:
                tag = strip_ino_tag(tag)
                if "user:" + tag not in args[item_id]["canto-tags"]:
                    inoreader_remove_tag(ino_id, tag)

on_hook("daemon_post_setattributes", post_setattributes)

def post_setconfigs(socket, args):
    if "feeds" in args:
        for feed in args["feeds"]:
            inoreader_add_sub(feed["url"], feed["name"])

on_hook("daemon_post_setconfigs", post_setconfigs)

def post_delconfigs(socket, args):
    if "feeds" in args:
        for feed in args["feeds"]:
            inoreader_del_sub(feed["url"])

on_hook("daemon_post_delconfigs", post_delconfigs)

def on_daemon_serving():
    log.debug("Synchronizing subscriptions.")
    ino_subs = inoreader_get_subs()

    for sub in ino_subs:
        url = sub["url"]
        name = sub["title"]

        for c_feed in config.json["feeds"]:
            if c_feed["url"] == url:
                break
        else:
            log.debug("New feed: %s" % url)
            call_hook("daemon_set_configs", [ None, { "feeds" : [ { "name" : name, "url" : url } ] } ])

    for c_feed in config.json["feeds"]:
        url = c_feed["url"]

        for sub in ino_subs:
            if sub["url"] == url:
                break
        else:
            log.debug("Old feed: %s" % url)
            call_hook("daemon_del_configs", [ None, { "feeds" : [ c_feed ] } ] )

on_hook("daemon_serving", on_daemon_serving)
