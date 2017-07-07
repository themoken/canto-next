# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .plugins import PluginHandler, Plugin, try_plugins, set_program
from .client import CantoClient
from .format import escsplit
from .hooks import call_hook

from xml.sax.saxutils import escape as xml_escape
import xml.parsers.expat
import feedparser
import traceback
import pprint
import time
import sys

import logging

def assign_to_dict(d, var, val):
    terms = escsplit(var, '.', 0, 0, True)
    cur = d

    for term in terms[:-1]:
        if term not in cur:
            cur[term] = {}
        elif type(cur[term]) != dict:
            return (False, "Term %s is not dict" % term)
        cur = cur[term]

    cur[terms[-1]] = val
    return (True, val)

def access_dict(d, var):
    terms = escsplit(var, '.', 0, 0, True)
    cur = d

    for term in terms[:-1]:
        if term not in cur:
            return (False, False)
        elif type(cur) != dict:
            return (False, False)
        cur = cur[term]

    if terms[-1] not in cur:
        return (False, False)
    return (True, cur[terms[-1]])

class DaemonRemotePlugin(Plugin):
    pass

class CantoRemote(PluginHandler, CantoClient):
    def __init__(self):
        self.plugin_attrs = {}

        # By default this will log to stderr.
        logging.basicConfig(
                format = "%(asctime)s : %(name)s -> %(message)s",
                datefmt = "%H:%M:%S",
                level = logging.ERROR
        )

        version = "canto-remote " + REPLACE_VERSION + " " + GIT_HASH
        optl = self.common_args("h", ["help"], version)
        if optl == -1:
            sys.exit(-1)

        if self.args(optl) == -1:
            sys.exit(-1)

        set_program("canto-remote")
        try_plugins(self.conf_dir, self.plugin_default, self.disabled_plugins,
                self.enabled_plugins)

        PluginHandler.__init__(self)
        self.plugin_class = DaemonRemotePlugin
        self.update_plugin_lookups()

        try:
            if self.port < 0:
                self.start_daemon()
                CantoClient.__init__(self, self.socket_path)
            else:
                CantoClient.__init__(self, None,\
                        port = self.port, address = self.addr)
        except Exception as e:
            print("Error: %s" % e)
            print(self.socket_path)
            sys.exit(-1)

        self.handle_args()

    def args(self, optlist):
        for opt, arg in optlist:
            if opt in [ "-h", "--help" ]:
                self.print_help()
                sys.exit(0)
        return 0

    def print_help(self):
        print("USAGE: canto-remote [options] ([command] [command-args])\n")
        self.print_commands()
        print("\n\t-h/--help\tThis help")
        print("\t-V/--version\tPrint version")
        print("\t-v/\t\tVerbose logging (for debug)")
        print("\t-D/--dir <dir>\tSet configuration directory.")
        print("\nPlugin control\n")
        print("\t--noplugins\t\t\t\tDisable plugins")
        print("\t--enableplugins 'plugin1 plugin2...'\tEnable single plugins (overrides --noplugins)")
        print("\t--disableplugins 'plugin1 plugin2...'\tDisable single plugins")
        print("\nNetwork control\n")
        print("NOTE: These should be used in conjunction with SSH port forwarding to be secure\n")
        print("\t-a/--address <IP>\tConnect to this address")
        print("\t-p/--port <port>\tConnect to this port")

    def print_commands(self):
        print("COMMANDS")
        print("\thelp - get help on a command")
        print("\taddfeed - subscribe to a new feed")
        print("\tlistfeeds - list all subscribed feeds")
        print("\tdelfeed - unsubscribe from a feed")
        print("\tstatus - print item counts")
        print("\tforce-update - refetch all feeds")
        print("\tconfig - change / query configuration variables")
        print("\tone-config - change / query one configuration variable")
        print("\texport - export feed list as OPML")
        print("\timport - import feed list from OPML")
        print("\tkill - cleanly kill the daemon")
        print("\tscript - run script")
        call_hook("remote_print_commands", [])

    def _wait_response(self, cmd):
        r = None
        while True:
            r = self.read()
            if type(r) == int:
                if r == 16:
                    print("Server hung up.")
                else:
                    print("Got code: %d" % r)
                print("Please check daemon-log for exception.")
                return
            elif type(r) == tuple:
                if not cmd:
                    return r
                if r[0] == cmd:
                    return r[1]
                elif r[0] == "ERRORS":
                    print("ERRORS!")
                    for key in list(r[1].keys()):
                        for val, err in r[1][key]:
                            print("%s -> %s: %s" % (key, val, err))
            elif r:
                print("Unknown return: %s" % r)
                break
        return None

    def _autoname(self, URL):
        extra_headers = { 'User-Agent' :\
                'Canto/0.9.0 + http://codezen.org/canto-ng' }
        try:
            content = feedparser.parse(URL, request_headers = extra_headers)
        except Exception as e:
            print("ERROR: Couldn't determine name: %s" % e)
            return None

        if "title" in content["feed"]:
            return content["feed"]["title"]
        else:
            print("Couldn't find title in feed!")

        return None

    def _get_feeds(self):
        self.write("CONFIGS", [ "feeds" ])
        c = self._wait_response("CONFIGS")

        return c["feeds"]

    def _addfeed(self, attrs):
        # Fill out
        if "name" not in attrs or not attrs["name"]:
            attrs["name"] = self._autoname(attrs["url"])
        if not attrs["name"]:
            print("Failed to autoname, please specify!")
            return False

        print("Adding feed %s - %s" % (attrs["url"], attrs["name"]))

        # SET merges the config options, so f will be appended to the
        # current value of "feeds", rather than overwriting.

        self.write("SETCONFIGS", { "feeds" : [ attrs ] } )
        self.write("PING", [])
        self._wait_response("PONG")

        return True

    def cmd_addfeed(self):
        """USAGE: canto-remote addfeed [URL] (option=value) ...
    Where URL is the feed's URL. You can also specify options for the feed:

        name = Feed name (if not specified remote will attempt to lookup)
        rate = Rate, in minutes, at which this feed should be fetched.

        username = Username (if necessary) for password protected feeds.
        password = Password for password protected feeds."""

        if len(sys.argv) < 2:
            return False

        feed = { "url" : sys.argv[1] }
        name = None

        # Grab any feedopts from the commandline.

        for arg in sys.argv[2:]:
            opt, val = escsplit(arg, "=", 1, 1, True)
            if not opt or not val:
                print("ERROR: can't parse '%s' as x=y setting." % arg)
                continue
            feed[opt] = val

        return self._addfeed(feed)

    def cmd_listfeeds(self):
        """USAGE: canto-remote listfeeds
    Lists all tracked feeds."""

        if len(sys.argv) > 1:
            return False

        for idx, f in enumerate(self._get_feeds()):
            s = ("%d. " % idx) + f["name"] + " "

            if "alias" in f:
                s += "(" + f["alias"] + ")"

            s += "\n" + f["url"] + "\n"
            print(s)

    def cmd_delfeed(self):
        """USAGE: canto-remote delfeed [URL|name|alias]
    Unsubscribe from a feed."""
        if len(sys.argv) != 2:
            return False

        term = sys.argv[1]

        for idx, f in enumerate(self._get_feeds()):
            matches = [ f["url"], f["name"], "%s" % idx]
            if "alias" in f:
                matches.append(f["alias"])

            if term in matches:
                print("Unsubscribing from %s" % f["url"])
                self.write("DELCONFIGS",  { "feeds" : [ f ] })

    def _config(self, args, evaled=False):
        sets = {}
        gets = []

        for arg in args:

            if "=" not in arg:
                gets.append(arg)
                continue

            var, val = escsplit(arg, "=", 1, 1)
            var = var.lstrip().rstrip()

            # We'll want to read back any value, regardless
            gets.append(var)

            if evaled:
                try:
                    val = eval(val, {},{})
                    val_ok = True
                except Exception as e:
                    print("Unable to eval value: %s - %s" % (val, e))
                    val_ok = False
            else:
                val_ok = True

            if val_ok:
                val_ok, ret = assign_to_dict(sets, var, val)
                if not val_ok:
                    print(ret)

        if sets:
            self.write("SETCONFIGS", sets)

        self.write("CONFIGS", [])
        c = self._wait_response("CONFIGS")

        for var in gets:
            valid, value = access_dict(c, var)
            if valid:
                print("%s = %s" % (var, value))
            else:
                print("Couldn't get %s!" % var)

        return True

    def cmd_one_config(self):
        """USAGE: canto-remote one-config [--eval] [option] ( = value)
    Where option is a full variable declaration like 'section.variable' and
    value is any string. If value is omitted, the current value will be printed.

    This differs from config as only one option can be set/got at a time, but
    it allows lax argument parsing (i.e. one-config CantoCurses.browser =
    firefox will work as expected, without quoting.)

    If the value you're setting is a type other than string, you must specify
    --eval and the value will be eval'd into a proper type.

    NOTE: validation is done by the client that uses the variable, canto-remote
    will let you give bad values, or even set values to non-existent
    variables."""

        if len(sys.argv) < 2:
            return False

        if sys.argv[1] == "--eval":
            return self._config([" ".join(sys.argv[2:])], True)
        return self._config([" ".join(sys.argv[1:])], False)

    def cmd_config(self):
        """USAGE: canto-remote config [--eval] [option](=value) ...
    Where option is a full variable declaration like 'section.variable' and
    value is any string. If value is omitted, the current value will be printed.

    This differs from one-config as multiple sets/gets can be done, but it is
    more strict in terms of argument parsing.

    If the value you're setting is a type other than string, you must specify
    --eval and the value will be eval'd into a proper type.

    NOTE: validation is done by the client that uses the variable, canto-remote
    will let you give bad values, or even set values to non-existent
    variables."""

        if len(sys.argv) < 2:
            return False

        if sys.argv[1] == "--eval":
            return self._config(sys.argv[2:], True)
        return self._config(sys.argv[1:], False)

    def cmd_export(self):
        """USAGE: canto-remote export

    This will print an OPML file to standard output."""

        print("""<opml version="1.0">""")
        print("""\t<body>""")
        for f in self._get_feeds():
            print("""\t\t<outline text="%s" xmlUrl="%s" type="rss" />""" %\
                (xml_escape(f["name"].replace("\"","\\\"")),
                 xml_escape(f["url"])))

        print("""\t</body>""")
        print("""</opml>""")

    def cmd_import(self):
        """USAGE: canto-remote import [OPML file]

    This will automatically import feeds from an OPML file, which can be
    generated by many different feed readers and other programs."""

        if len(sys.argv) != 2:
            return False

        opmlpath = sys.argv[1]

        try:
            data = open(opmlpath, "r").read()
        except Exception as e:
            print("Couldn't read OPML file:")
            traceback.print_exc()
            return

        feeds = []
        def parse_opml(name, attrs):
            # Skip elements we don't care about.
            if name != "outline":
                return

            # Skip outline elements with unknown type.
            if "type" in attrs and attrs["type"] not in ["pie","rss"]:
                return

            # Skip outline elements with type, but no URL
            if "xmlUrl" not in attrs:
                return

            f = { "url" : attrs["xmlUrl"], "name" : None }
            if "text" in attrs:
                f["name"] = attrs["text"]

            feeds.append(f)

        parser = xml.parsers.expat.ParserCreate()
        parser.StartElementHandler = parse_opml
        parser.Parse(data.encode("UTF-8"), 1)

        for feed in feeds:
            self._addfeed(feed)

    def cmd_script(self):
        """USAGE canto-remote script (scriptfile)

    Run script from scriptfile or stdin.

    Note: This is intended for testing and does not gracefully handle errors."""

        if len(sys.argv) not in [1, 2]:
            return False

        if len(sys.argv) == 1:
            lines = sys.stdin.readlines()
        else:
            f = open(sys.argv[1], "r")
            lines = f.readlines()
            f.close()

        pp = pprint.PrettyPrinter()

        for line in lines:
            line = line[:-1].lstrip()
            print(line)
            sys.__stdout__.flush()

            # Wait for n responses.

            if line.startswith("REMOTE_WAIT "):
                num = int(line.split(" ", 1)[-1])
                for i in range(num):
                    r = self._wait_response(None)
                    print(pp.pformat(r))
                    sys.__stdout__.flush()

            elif line.startswith("REMOTE_IGNORE "):
                num = int(line.split(" ", 1)[-1])
                for i in range(num):
                    self._wait_response(None)

            # Hang with socket open so that the daemon thinks
            # we're using any data we've requested. Script runners
            # must be smart enough to signal-kill this remote.

            elif line.startswith("REMOTE_HANG"):
                while True:
                    time.sleep(1000)

            # Skip comments / blank

            elif line == '' or line.startswith("#"):
                continue

            else:
                cmd, arg = line.split(' ', 1)
                self.write(cmd, eval(arg))

    def cmd_kill(self):
        """USAGE: canto-remote kill

    Cleanly kill the connected daemon."""

        self.write("DIE", {})

    def cmd_force_update(self):
        """USAGE: canto-remote force-update

    Force fetch of all feeds."""

        self.write("FORCEUPDATE", {})

    def _numstate(self, tag, state):
        self.write("AUTOATTR", [ "canto-state" ])
        self.write("ITEMS", [ tag ])

        items = []

        cmd, r = self._wait_response(None)
        while cmd != "ITEMSDONE":
            if cmd == "ITEMS":
                items.extend(r[tag])
            cmd, r = self._wait_response(None)

        if len(items) == 0:
            return 0

        attrs = self._wait_response("ATTRIBUTES")

        if state == "unread":
            return len([ x for x in items if "read" not in attrs[x]["canto-state"]])
        elif state == "read":
            return len([ x for x in items if "read" in attrs[x]["canto-state"]])
        else:
            return len(items)

    def cmd_status(self):
        """USAGE: canto-remote status (--tag=tag) (--read|--total|--tags)

    Print the number of unread items tracked by the daemon.

    --tags can be given to print a summary for all existing tags

    --tag can be given to print the number of items in that particular tag
    (i.e. "maintag:Slashdot", "user:cool")

    --read can be given to print the number of read items
    --total can be given to print the total number of items

    NOTE: This is still subject to defaults.global_transform, and defined tag
    transforms, so if you're using filter_read, for example, it will never
    return a single read item (so --total will have no effect and --read will
    always return 0)."""

        state = "unread"
        if "--read" in sys.argv:
            state = "read"
        if "--total" in sys.argv:
            state = "all"

        self.write("LISTTAGS","")
        t = self._wait_response("LISTTAGS")

        if "--tags" in sys.argv:
            for tag in t:
                print("%s : %s" % (tag, self._numstate(tag, state)))
        elif "--tag" in sys.argv:
            if "--tag" == sys.argv[-1]:
                print("--tag must be followed by a tag name")
                sys.exit(-1)

            tag = sys.argv[sys.argv.index("--tag") + 1]
            if tag not in t:
                print("Unknown tag %s - use --tags to list known tags" % tag)
                sys.exit(-1)

            print("%s : %s" % (tag, self._numstate(tag, state)))
        else:
            print("%s" % sum([self._numstate(tag, state) for tag in t if tag.startswith("maintag:")]))

    def cmd_help(self):
        """USAGE: canto-remote help [command]"""
        if len(sys.argv) < 2:
            return False

        command = "cmd_" + sys.argv[1].replace("-","_")

        if hasattr(self, command):
            print(getattr(self, command).__doc__)
        else:
            print(self.cmd_help.__doc__)
            self.print_commands()

    def handle_args(self):
        if len(sys.argv) < 1:
            self.print_help()
            return

        command = "cmd_" + sys.argv[0].replace("-","_")

        if hasattr(self, command):
            func = getattr(self, command)
            r = func()
            if r == False:
                print(func.__doc__)
        else:
            self.print_help()
