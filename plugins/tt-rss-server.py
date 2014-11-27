#Canto TT-RSS Server Compatibility Plugin
# by Jack Miller
# v0.1 (WIP)

# This will allow you to connect to canto-daemon with a TT-RSS compatible
# client.

# This plugin is a work in progress, and should be considered experimental and
# insecure for use over the open internet.

LOGIN="user"
PASSWORD="password"

from canto_next.feed import allfeeds

from http.server import HTTPServer, BaseHTTPRequestHandler
from html.parser import HTMLParser

from threading import Thread
import logging
import base64
import json
import os

log = logging.getLogger("TTRSS-SERVER")

class HTMLSanitizer(HTMLParser):
    def __init__(self):
        self.reset()
        self.strict = False
        self.convert_charrefs = False
        self.data = ""

        # Taken from TT-RSS functions2.php
        self.allowed = ['a', 'address', 'audio', 'article', 'aside',\
            'b', 'bdi', 'bdo', 'big', 'blockquote', 'body', 'br',\
            'caption', 'cite', 'center', 'code', 'col', 'colgroup',\
            'data', 'dd', 'del', 'details', 'div', 'dl', 'font',\
            'dt', 'em', 'footer', 'figure', 'figcaption',\
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'html', 'i',\
            'img', 'ins', 'kbd', 'li', 'main', 'mark', 'nav', 'noscript',\
            'ol', 'p', 'pre', 'q', 'ruby', 'rp', 'rt', 's', 'samp', 'section',\
            'small', 'source', 'span', 'strike', 'strong', 'sub', 'summary',\
            'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'time',\
            'tr', 'track', 'tt', 'u', 'ul', 'var', 'wbr', 'video']

        self.disallowed_attributes = [ "id", "style", "class" ]

    def attr_dict(self, attrs):
        d = {}
        for k, v in attrs:
            d[k] = v
        return d

    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed:
            return

        attrs = self.attr_dict(attrs)

        for attr in self.disallowed_attributes:
            if attr in attrs:
                del attrs[attr]

        res = "<" + tag
        for attr in attrs:
            res += " " + attr + '="' + attrs[attr] + '"'
        res += ">"

        self.data += res

    def handle_data(self, d):
        self.data += d

    def handle_endtag(self, tag):
        if tag not in self.allowed:
            return
        if tag not in [ "img", "br" ]:
            self.data += '</' + tag + '>'

    def get_data(self):
        return self.data

def sanitize(html):
    s = HTMLSanitizer()
    s.feed(html)
    return s.get_data()

class CantoTTRSS(BaseHTTPRequestHandler):
    def __init__(self, *args):
        self.seq = 0
        self.valid_sessions = []

        BaseHTTPRequestHandler.__init__(self, *args)

    def op_login(self, post_body):
        if post_body['user'] != LOGIN or post_body['password'] != PASSWORD:
            self.send_response(401, "Not Authorized")
            self.end_headers()
            return

        session_id = base64.b64encode(os.urandom(16)).decode("UTF-8")

        self.ok_response({'session_id' : session_id })

    def op_getFeeds(self, post_body):
        resp = []
        for i, feed in enumerate(allfeeds.get_feeds()):
            content = {}
            content["feed_url"] = feed.URL
            content["id"] = str(i)
            content["title"] = feed.name
            resp.append(content)

        self.ok_response(resp)

    def op_getHeadlines(self, post_body):
        log.debug("GETHEAD")
        feed = allfeeds.get_feeds()[int(post_body['feed_id'])]
        items = feed.shelf[feed.URL]["entries"]

        skip = 0
        if 'skip' in post_body:
            skip = int(post_body['skip'])

        if len(items) > skip:
            items = items[skip:]
        else:
            items = []

        limit = 200
        if 'limit' in post_body:
            limit = int(post_body['limit'])

        if len(items) > limit:
            items = items[:limit]

        resp = []

        base_url = urlparse(feed.URL)[1]

        for i, item in enumerate(items):
            content = {}

            title = sanitize(item["title"])
            summ = sanitize("<html><body>" + item["summary"] + "</body></html>")

            content["id"] = (skip + i)
            content["title"] = title
            content["link"] = item["link"]
            content["updated"] = int(item["canto_update"])
            content["content"] = summ

            unread = True
            if "canto-state" in item and "read" in item["canto-state"]:
                unread = False
            content["unread"] = unread

            resp.append(content)

        self.ok_response(resp)

    def ok_response(self, content):
        resp = json.dumps({ 'seq' : self.seq, 'status' : 0, 'content' : content }).encode("UTF-8")
        self.send_response(200, "OK")
        self.send_header("Content-Length", len(resp))
        self.end_headers()

        while resp:
            r = self.wfile.write(resp)
            resp = resp[r:]

    def do_POST(self):
        content_len = int(self.headers['content-length'])
        post_body = self.rfile.read(content_len)

        log.debug(self.path)
        log.debug(self.headers)
        post_body = json.loads(post_body.decode("ascii"))

        log.debug(post_body)

        if 'op' in post_body:
            handler = 'op_' + post_body['op']
            if hasattr(self, handler):
                getattr(self, handler)(post_body)
        else:
            self.send_response(501)

class CantoTTRSSThread(Thread):
    def run(self):
        server_address = ('', 7071)
        httpd = HTTPServer(server_address, CantoTTRSS)
        httpd.serve_forever()

CantoFrontEndTTRSS = CantoTTRSSThread()
CantoFrontEndTTRSS.daemon = True
CantoFrontEndTTRSS.start()
