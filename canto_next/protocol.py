# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2014 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import logging
import socket
import select
import errno
import getopt
import struct
import shlex
import json
import time
import sys
import os

log = logging.getLogger('SOCKET')

class CantoSocket:
    def __init__(self, socket_name, **kwargs):

        self.socket_name = socket_name

        if "server" in kwargs and kwargs["server"]:
            self.server = True
        else:
            self.server = False

        if "port" in kwargs:
            self.port = kwargs["port"]
        else:
            self.port = 0

        if "interface" in kwargs:
            self.interface = kwargs["interface"]
        else:
            self.interface = ''

        if "address" in kwargs:
            self.address = kwargs["address"]
        else:
            self.address = None

        self.sockets = []

        self.connect()

    # Handle options common to all servers and clients

    def common_args(self, extrashort = "", extralong = [], version = ""):
        self.verbosity = 0
        self.port = -1
        self.addr = None
        self.disabled_plugins = []
        self.enabled_plugins = []
        self.plugin_default = True

        try:
            optlist, sys.argv =\
                getopt.getopt(sys.argv[1:], 'D:p:a:vV' + extrashort, ["dir=",
                "port=", "address=","version", "noplugins","enableplugins=",
                "disableplugins="] + extralong)

        except getopt.GetoptError as e:
            log.error("Error: %s" % e.msg)
            return -1

        old_path = os.path.expanduser("~/.canto-ng")

        if os.path.exists(old_path):
            self.conf_dir = old_path
        else:
            if "XDG_CONFIG_HOME" in os.environ:
                xdg_path = os.environ["XDG_CONFIG_HOME"]
            else:
                xdg_path = "~/.config"

            xdg_path = os.path.expanduser(xdg_path)
            self.conf_dir = xdg_path + "/canto"

        self.location_args = []

        for opt, arg in optlist:
            if opt in [ "-D", "--dir"]:
                self.conf_dir = os.path.expanduser(arg)
                self.conf_dir = os.path.realpath(self.conf_dir)
                self.location_args += [ opt, arg ]

            elif opt in ["-V", "--version"]:
                print(version)
                sys.exit(0)

            elif opt in ["-v"]:
                self.verbosity += 1

            elif opt in [ "-p", "--port"]:
                try:
                    self.port = int(arg)
                    if self.port < 0:
                        raise Exception
                except:
                    log.error("Error: Port must be >0 integer.")
                    return -1

                # Assume loopback if address hasn't been set yet.
                if self.addr == None:
                    self.addr = "127.0.0.1"

                self.location_args += [ opt, arg ]

            elif opt in [ "-a", "--address"]:
                self.addr = arg
                self.location_args += [ opt, arg ]

            elif opt in ['--noplugins']:
                self.plugin_default = False

            elif opt in ['--disableplugins']:
                self.disabled_plugins = shlex.split(arg)

            elif opt in ['--enableplugins']:
                self.enabled_plugins = shlex.split(arg)

        self.socket_path = self.conf_dir + "/.canto_socket"

        return optlist

    # Server setup, potentially both unix and inet sockets.
    def connect(self):
        if self.server:
            if self.socket_name:
                # Remove old unix socket.
                if os.path.exists(self.socket_name):
                    os.remove(self.socket_name)

                # Setup new socket.
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.setblocking(0)
                sock.bind(self.socket_name)
                sock.listen(5)

            # Net socket setup.
            if self.port > 0:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(0)

                sock.bind((self.interface, self.port))
                sock.listen(5)

        # Client setup, can only do unix or inet, not both.

        else:
            if self.address and self.port > 0:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                addr = (self.address, self.port)
            else:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                addr = self.socket_name

            tries = 10

            while tries > 0:
                try:
                    sock.connect(addr)
                    break
                except Exception as e:
                    if e.args[0] != errno.ECONNREFUSED or tries == 1:
                        raise
                time.sleep(1)
                tries -= 1

        self.sockets.append(sock)
        return sock

    # Setup poll.poll() object to watch for read status on conn.
    def read_mode(self, poll, conn):
        poll.register(conn.fileno(),\
                select.POLLIN | select.POLLHUP | select.POLLERR |\
                select.POLLPRI)

    # Setup poll.poll() object to watch for write status on conn.
    def write_mode(self, poll, conn):
        poll.register(conn.fileno(),\
                select.POLLOUT | select.POLLHUP | select.POLLERR |\
                select.POLLNVAL)

    # Take raw data, return (cmd, args) tuple or None if not enough data.
    def parse(self, conn, data):
        try:
            cmd, args = eval(repr(json.loads(data)), {}, {})
        except:
            log.error("Failed to parse message: %s" % data)
        else:
            log.debug("\n\nRead:\n%s", json.dumps((cmd, args), indent=4, sort_keys=True))
            return (cmd, args)

    # Reads from a connection, returns:
    # 1) (cmd, args) from self.parse if possible.
    # 2) None, if there was not enough data read.
    # 3) select.POLLHUP if the connection is dead.

    def do_read(self, conn, timeout=None):
        r = self._do_read(conn, timeout)
        if r == select.POLLHUP:
            self.disconnected(conn)
        return r

    def _do_read(self, conn, timeout):
        poll = select.poll()

        try:
            self.read_mode(poll, conn)
        except:
            log.error("Error putting conn in read mode.")
            log.error("Interpreting as HUP")
            return select.POLLHUP

        # We only care about the first (only) descriptor's event
        try:
            p = poll.poll(timeout)
        except select.error as e:
            if e.args[0] == errno.EINTR:
                return
            log.debug("Raising error: %s", e[1])
            raise

        if timeout and not p:
            return

        e = p[0][1]

        log.debug("E: %d", e)
        if e & select.POLLERR:
            log.debug("Read ERR")
            return select.POLLHUP
        if e & (select.POLLIN | select.POLLPRI):
            message = ""
            size = struct.unpack('!q', conn.recv(8))[0]
            while size:
                try:
                    frag = conn.recv(min((4096, size)))
                    size -= len(frag)
                    message += frag.decode()
                except Exception as e:
                    if e.args[0] == errno.EINTR:
                        continue

                    log.error("Error receiving: %s" % e)
                    log.error("Interpreting as HUP")
                    return select.POLLHUP

            # Never get POLLRDHUP on INET sockets, so
            # use POLLIN with no data as POLLHUP

            if not message:
                log.debug("Read POLLIN with no data")
                return select.POLLHUP

            return self.parse(conn, message)

        # Parse POLLHUP last so if we still got POLLIN, any data
        # is still retrieved from the socket.
        if e & select.POLLHUP:
            log.debug("Read HUP")
            return select.POLLHUP

        # Non-empty, but not anything we're interested in?
        log.debug("Unknown poll.poll() return")
        return select.POLLHUP

    # Writes a (cmd, args) to a single connection, returns:
    # 1) None if the write completed.
    # 2) select.POLLHUP is the connection is dead.

    def do_write(self, conn, cmd, args):
        r = self._do_write(conn, cmd, args)
        if r == select.POLLHUP:
            self.disconnected(conn)
        return r

    def _do_write(self, conn, cmd, args):
        log.debug("\n\nWrite:\n%s\n", json.dumps((cmd, args), indent=4, sort_keys=True))

        message = json.dumps((cmd, args)).encode("UTF-8")
        size = struct.pack("!q", len(message))
        message = size + message

        poll = select.poll()
        tosend = message

        try:
            self.write_mode(poll, conn)
        except:
            log.error("Error putting conn in write mode.")
            log.error("Interpreting as HUP")
            return select.POLLHUP

        eintr_count = 0

        while tosend:

            # Again, we only care about the first descriptor's mask

            try:
                p = poll.poll()
            except select.error as e:
                if e.args[0] == errno.EINTR:
                    eintr_count += 1
                    if eintr_count >= 3:
                        log.error("conn %s appears valid, but unresponsive." % conn)
                        log.error("Closing conn, please check client.")
                        conn.close()
                        return select.POLLHUP
                    continue
                log.error("Raising error: %s" % e[1])
                raise

            if not p:
                continue
            e = p[0][1]

            if e & select.POLLHUP:
                log.debug("Write HUP")
                return select.POLLHUP
            if e & select.POLLNVAL:
                log.debug("Write NVAL")
                return select.POLLHUP
            if e & select.POLLERR:
                log.debug("Write ERR")
                return select.POLLHUP
            if e & select.POLLOUT:
                try:
                    sent = conn.send(tosend)
                except Exception as e:
                    if e.args[0] == errno.EINTR:
                        continue
                    log.error("Error sending: %s" % e[1])
                    log.error("Interpreting as HUP")
                    return select.POLLHUP

                tosend = tosend[sent:]
                log.debug("Sent %d bytes.", sent)

    def disconnected(self, conn):
        pass
