# Canto Inoreader Plugin
# by Jack Miller
# v0.4

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
# - You must have a standard Inoreader account, not an OAuth (Google/Facebook
# login).

# CONFIGURATION

# Inoreader credentials

EMAIL="somebody@somewhere.com"
PASSWORD="passw0rd"

# You don't *have* to change these, but the API is rate limited. So if you want
# to avoid rate limit issues, register your own application Preferences ->
# Developer options on the Inoreader site and replace these.

APP_ID="1000001299"
APP_KEY="i0UOUtLQjj2WTre8WA3a9GWt_cgDhpkO"

BASE_URL="https://www.inoreader.com/reader/"

# === You shouldn't have to change anything past this line. ===

from canto_next.plugins import check_program

check_program("canto-daemon")

from canto_next.fetch import DaemonFetchThreadPlugin
from canto_next.feed import DaemonFeedPlugin, allfeeds
from canto_next.hooks import call_hook, on_hook
from canto_next.config import config

from urllib.parse import urlencode, quote
import traceback
import requests
import logging
import time
import json

log = logging.getLogger("SYNC-INOREADER")

class InoreaderReqFailed(Exception):
    pass

class InoreaderAuthFailed(Exception):
    pass

class CantoInoreaderAPI():
    def __init__(self):
        self.extra_headers = {
                "User-Agent" : "Canto/0.9.0 + http://codezen.org/canto-ng",
                "AppKey" : APP_KEY,
                "AppID" : APP_ID,
        }

        try:
            self.authorization = self.auth()
        except:
            self.authorization = None

        self.dead = False

        self.add_tags_queued = {}
        self.del_tags_queued = {}

    def auth(self):
        headers = self.extra_headers.copy()
        headers['Email'] = EMAIL
        headers['Passwd'] = PASSWORD

        try:
            r = requests.get("https://www.inoreader.com/accounts/ClientLogin", headers, timeout=1)
        except Exception as e:
            raise InoreaderReqFailed(str(e))

        if r.status_code != 200:
            raise InoreaderAuthFailed("Failed to authorize: [%s] %s" % (r.status_code, r.text))

        for line in r.text.splitlines():
            if line.startswith("Auth="):
                log.debug("authorization: %s", line[5:])
                return line[5:]

        raise InoreaderAuthFailed("Failed to find Auth= in auth response")

    def inoreader_req(self, path, query = {}):
        tries = 3
        r = {}

        while tries and not self.dead:
            tries -= 1
            if not self.authorization:
                try:
                    self.authorization = self.auth()
                except InoreaderReqFailed as e:
                    log.debug("Auth request failed: %s", e)
                    continue
                except InoreaderAuthFailed:
                    log.error("Inoreader authorization failed, please check your credentials in sync-inoreader.py")
                    self.dead = True
                    raise

            headers = self.extra_headers.copy()
            headers["Authorization"] = "GoogleLogin auth=" + self.authorization

            try:
                r = requests.get(BASE_URL + path, params=query, headers=headers, timeout=1)
            except requests.exceptions.Timeout:
                raise InoreaderReqFailed

            if r.status_code != 200:
                log.debug("STATUS %s", r.status_code)
                log.debug(r.headers)
                log.debug(r.text)
            else:
                return r

            # No authorization, attempt to get another code on the next try.

            if r.status_code == 401:
                self.authorization = None
            elif r.status_code == 429:
                log.error("Inoreader rate limit reached.")
                self.dead = True
            elif r.status_code == 503:
                log.error("Inoreader appears down, state may be lost")

        raise InoreaderReqFailed

    # Convert special tags into /state/com.google/tag and others into
    # /label/tag, useful when matching without knowing the user.

    def full_ino_tag_suffix(self, tag):
        if tag in ["read", "starred", "fresh"]:
            return "/state/com.google/" + tag
        return "/label/" + tag

    # Add the user/- prefix to go upstream to Inoreader.

    def full_ino_tag(self, tag):
        return "user/-" + self.full_ino_tag_suffix(tag)

    # Do the opposite, convert an Inoreader tag into a natural name.  (i.e.)
    # /user/whatever/state/com.google/read -> read

    def strip_ino_tag(self, tag):
        tag = tag.split("/", 3)
        if tag[2] == "state":
            return tag[3].split("/", 1)[1]
        return tag[3]

    # Return whether Inoreader data includes this natural tag

    def has_tag(self, item, tag):
        if "canto_inoreader_categories" not in item:
            return False

        suff = self.full_ino_tag_suffix(tag)
        for category in item["canto_inoreader_categories"]:
            if category.endswith(suff):
                return True
        return False

    def add_tag(self, item, tag):
        ino_id = item["canto_inoreader_id"]
        if not self.has_tag(item, tag):
            if tag in self.add_tags_queued:
                self.add_tags_queued[tag].append(ino_id)
            else:
                self.add_tags_queued[tag] = [ino_id]

    def remove_tag(self, item, tag):
        ino_id = item["canto_inoreader_id"]
        if self.has_tag(item, tag):
            if tag in self.del_tags_queued:
                self.del_tags_queued[tag].append(ino_id)
            else:
                self.del_tags_queued[tag] = [ino_id]

    def _urllimit(self, prefix, ino_ids):
        t = prefix
        l = len(t)

        for i, ino_id in enumerate(ino_ids):
            if l + len(ino_id) > 2048:
                self.inoreader_req(t)
                return ino_ids[i:]
            t += ino_id
            l += len(ino_id)

        self.inoreader_req(t)
        return []

    def flush_changes(self):
        for key in self.add_tags_queued:
            to_add = [ "&i=" + quote(x) for x in self.add_tags_queued[key]]
            while to_add:
                to_add = self._urllimit("api/0/edit-tag?a=" + quote(self.full_ino_tag(key)), to_add)

        for key in self.del_tags_queued:
            to_del = [ "&i=" + quote(x) for x in self.del_tags_queued[key]]
            while to_del:
                to_del = self._urllimit("api/0/edit-tag?r=" + quote(self.full_ino_tag(key)), to_del)

        self.add_tags_queued = {}
        self.del_tags_queued = {}

    def get_subs(self):
        return self.inoreader_req("api/0/subscription/list").json()["subscriptions"]

    def add_sub(self, feed_url, title):
        query = {
            "ac" : "subscribe",
            "s" : "feed/" + feed_url,
            "t" : title
        }

        self.inoreader_req("api/0/subscription/edit", query)

    def del_sub(self, feed_url):
        query = {
            "ac" : "unsubscribe",
            "s" : "feed/" + feed_url
        }

        self.inoreader_req("api/0/subscription/edit", query)

api = CantoInoreaderAPI()

# Given a change set, and the current attributes of a canto item, tell
# Inoreader about it.

def sync_state_to(changes, attrs, add_only = False):
    if "canto-state" in changes:
        if "read" in changes["canto-state"]:
            api.add_tag(attrs, "read")
        elif not add_only:
            if api.has_tag(attrs, "read"):
                api.remove_tag(attrs, "read")

    if "canto-tags" in changes:
        for tag in changes["canto-tags"]:
            tag = tag.split(":", 1)[1] # strip user: or category: prefix
            if not api.has_tag(attrs, tag):
                api.add_tag(attrs, tag)

        if add_only:
            return

        for tag in attrs["canto_inoreader_categories"]:
            tag = api.strip_ino_tag(tag)
            if "user:" + tag not in changes["canto-tags"]:
                api.remove_tag(attrs, tag)

class CantoFeedInoReader(DaemonFeedPlugin):
    def __init__(self, feed):
        self.plugin_attrs = { "edit_inoreader_sync" : self.edit_inoreader_sync,
                "additems_inoreader" : self.additems_inoreader }
        self.feed = feed
        self.ino_data = None

    def _list_add(self, item, attr, new):
        if attr not in item:
            item[attr] = [ new ]
        elif new not in item[attr]:
            item[attr].append(new)

    def add_utag(self, item, tags_to_add, tag):
        self._list_add(item, "canto-tags", "user:" + tag)
        tags_to_add.append((item, "user:" + tag))

    def add_state(self, item, state):
        self._list_add(item, "canto-state", state)

    def additems_inoreader(self, feed, newcontent, tags_to_add, tags_to_remove, remove_items):
        stream_id = quote("feed/" + feed.URL, [])

        query = { "n" : 1000 }

        # Collect all of the items

        self.ino_data = []

        content_path = "api/0/stream/contents/" + stream_id

        try:
            r = api.inoreader_req(content_path, query).json()
            self.ino_data.extend(r["items"])
        except (InoreaderAuthFailed, InoreaderReqFailed):
            return (tags_to_add, tags_to_remove, remove_items)
        except Exception as e:
            log.debug("EXCEPT: %s", traceback.format_exc())
            raise

        # Find items that were inserted last time, and remove them, potentially
        # adding them to our fresh Inoreader data.

        # This keeps us from getting dupes when Inoreader finds an item, we
        # insert it, and then a real copy comes to canto but canto doesn't
        # detect the dupe since the ids are different.

        for canto_entry in newcontent["entries"][:]:
            if "canto-from-inoreader" not in canto_entry:
                continue

            remove_items.append(canto_entry)
            tags_to_add = [ x for x in tags_to_add if x[0] != canto_entry]

            newcontent["entries"].remove(canto_entry)

            for ino_entry in self.ino_data[:]:
                if canto_entry["id"] == ino_entry["id"]:
                    break
            else:
                self.ino_data.append(canto_entry)

        # Now insert (or re-insert) items that aren't already in our data.

        # NOTE: It's okay if re-inserted items are also in remove_ids, since
        # that's processed first, and will be cancelled out by adding the tags
        # afterwards.

        for ino_entry in self.ino_data:
            for canto_entry in newcontent["entries"]:
                if ino_entry["canonical"][0]["href"] != canto_entry["link"]:
                    continue
                if ino_entry["id"] == canto_entry["id"]:
                    canto_entry["canto-from-inoreader"] = True
                break
            else:
                if "canto-from-inoreader" not in ino_entry:
                    # feedparser compatibility
                    ino_entry["summary"] = ino_entry["summary"]["content"]
                    ino_entry["link"] = ino_entry["canonical"][0]["href"]

                    # mark this item as from inoreader (missing from feed)
                    ino_entry["canto-from-inoreader"] = True

                newcontent["entries"].append(ino_entry)
                tags_to_add.append((ino_entry, "maintag:" + feed.name ))

        return (tags_to_add, tags_to_remove, remove_items)

    def edit_inoreader_sync(self, feed, newcontent, tags_to_add, tags_to_remove, remove_items):

        # Add inoreader_id/categories information to the items

        # This is very similar to the loop in additems_inoreader, but needs to
        # be separate in case other plugins add items that inoreader might
        # track.

        for ino_entry in self.ino_data:
            for canto_entry in newcontent["entries"][:]:
                if ino_entry["canonical"][0]["href"] != canto_entry["link"]:
                    continue
                canto_entry["canto_inoreader_id"] = ino_entry["id"]
                canto_entry["canto_inoreader_categories"] = ino_entry["categories"]
                break

        # Drop the data.
        self.ino_data = None

        for entry in newcontent["entries"]:
            # If we didn't get an id for this item, skip it

            if "canto_inoreader_id" not in entry:
                continue

            for category in entry["canto_inoreader_categories"]:
                if category.endswith("/state/com.google/read"):
                    self.add_state(entry, "read")
                    continue

                cat = category.split("/", 3)
                if len(cat) < 4:
                    log.debug("Weird category? %s", cat)
                    continue

                if cat[2] == "state":
                    if cat[3] == "com.google/starred":
                        self.add_utag(entry, tags_to_add, "starred")
                elif cat[2] == "label":
                    self.add_utag(entry, tags_to_add, cat[3])

            # If this is the first time we've paired an item up with its
            # Inoreader data, our state is better, so sync it to Inoreader, and
            # then skip the remainder of the logic to remove canto state/tags

            if "canto-inoreader-sync" not in entry:
                sync_state_to(entry, entry, True)
                entry["canto-inoreader-sync"] = True
                continue

            if "canto-state" not in entry or type(entry["canto-state"]) != list:
                continue

            # It appears that if an item is "fresh" it will resist all attempts
            # to set it as read?

            if "read" in entry["canto-state"] and not\
                    (api.has_tag(entry, "read") or api.has_tag(entry, "fresh")):
                log.debug("Marking unread from Inoreader")
                entry["canto-state"].remove("read")

            if "canto-tags" not in entry or type(entry["canto-tags"]) != list:
                continue

            for tag in entry["canto-tags"][:]:
                if not api.has_tag(entry, tag.split(":", 1)[1]):
                    entry["canto-tags"].remove(tag)
                    tags_to_remove.append((entry, tag))

        api.flush_changes()
        return (tags_to_add, tags_to_remove, remove_items)

# For canto communicating to Inoreader, we tap into the relevant hooks to
# pickup state / tag changes, and convert that into Inoreader API calls.

def post_setattributes(socket, args):
    for item_id in args.keys():
        dict_id = json.loads(item_id)

        feed = allfeeds.get_feed(dict_id["URL"])

        attrs = feed.get_attributes([item_id], { item_id :\
                ["canto_inoreader_id", "canto_inoreader_categories", "canto-state", "canto-tags"] })
        attrs = attrs[item_id]

        # If the canto_inoreader_id isn't right (likely empty since get_attributes
        # will sub in "") then skip synchronizing this item.

        ino_id = attrs["canto_inoreader_id"]
        if not ino_id.startswith("tag:google.com,2005:reader/item/"):
            continue

        sync_state_to(args[item_id], attrs)

    api.flush_changes()

on_hook("daemon_post_setattributes", post_setattributes)

def post_setconfigs(socket, args):
    if "feeds" in args:
        for feed in args["feeds"]:
            api.add_sub(feed["url"], feed["name"])

on_hook("daemon_post_setconfigs", post_setconfigs)

def post_delconfigs(socket, args):
    if "feeds" in args:
        for feed in args["feeds"]:
            api.del_sub(feed["url"])

on_hook("daemon_post_delconfigs", post_delconfigs)

# Do the initial feed synchronization. This only occurs once per run, and
# assumes Inoreader knows everything.

def on_daemon_serving():
    log.debug("Synchronizing subscriptions.")
    ino_subs = api.get_subs()

    for c_feed in config.json["feeds"]:
        url = c_feed["url"]

        for sub in ino_subs:
            if sub["url"] == url:
                break
        else:
            log.debug("Old feed: %s", url)
            call_hook("daemon_del_configs", [ None, { "feeds" : [ c_feed ] } ] )

    for sub in ino_subs:
        url = sub["url"]
        name = sub["title"]

        for c_feed in config.json["feeds"]:
            if c_feed["url"] == url:
                break
            if c_feed["name"] == name:
                log.info("Found feed with same name, but not URL? Skipping.")
                break
        else:
            log.debug("New feed: %s", url)
            call_hook("daemon_set_configs", [ None, { "feeds" : [ { "name" : name, "url" : url } ] } ])


on_hook("daemon_serving", on_daemon_serving)
