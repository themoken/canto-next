# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .hooks import on_hook

from threading import Thread
import logging
import socket
import select
import errno
import json
import time
import os

PROTO_TERMINATOR='\x00'

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

        # Holster for partial reads.
        self.fragments = { }

        on_hook("new_socket", self.prot_new_frag)
        on_hook("kill_socket", self.prot_kill_frag)

        self.connect()

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
                self.sockets.append(sock)

            # Net socket setup.
            if self.port > 0:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(0)

                sock.bind((self.interface, self.port))
                sock.listen(5)
                self.sockets.append(sock)

        # Client setup, can only do unix or inet, not both.

        else:
            if self.address and self.port > 0:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                addr = (self.address, self.port)
            else:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                addr = self.socket_name

            self.sockets.append(sock)
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

    # Setup poll.poll() object to watch for read status on conn.
    def read_mode(self, poll, conn):
        poll.register(conn.fileno(),\
                select.POLLIN | select.POLLHUP | select.POLLERR)

    # Setup poll.poll() object to watch for write status on conn.
    def write_mode(self, poll, conn):
        poll.register(conn.fileno(),\
                select.POLLOUT | select.POLLHUP | select.POLLERR)

    def prot_new_frag(self, newconn):
        if newconn not in self.fragments:
            self.fragments[newconn] = ""

    def prot_kill_frag(self, deadconn):
        if deadconn in self.fragments:
            del self.fragments[deadconn]

    # Take raw data, return (cmd, args) tuple or None if not enough data.
    def parse(self, conn, data):

        self.fragments[conn] += data

        if PROTO_TERMINATOR not in self.fragments[conn]:
            return None

        message, self.fragments[conn] =\
                self.fragments[conn].split(PROTO_TERMINATOR, 1)

        try:
            cmd, args = eval(repr(json.loads(message)), {}, {})
            return (cmd, args)
        except:
            log.error("Failed to parse message: %s" % message)

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
        if self.fragments[conn] and PROTO_TERMINATOR in self.fragments[conn]:
            return self.parse(conn, "") # <- already uses self.fragments

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
            log.debug("Raising error: %s" % e[1])
            raise

        if timeout and not p:
            return

        e = p[0][1]

        log.debug("E: %d" % e)
        if e & select.POLLERR:
            log.debug("Read ERR")
            return select.POLLHUP
        if e & select.POLLIN:
            try:
                fragment = conn.recv(1024).decode()
            except Exception as e:
                if e.args[0] == errno.EINTR:
                    return
                log.error("Error sending: %s" % e)
                log.error("Interpreting as HUP")
                return select.POLLHUP

            # Never get POLLRDHUP on INET sockets, so
            # use POLLIN with no data as POLLHUP
            if not fragment:
                log.debug("Read POLLIN with no data")
                return select.POLLHUP

            log.debug("Read Buffer: %s" % fragment.replace("\0",""))
            return self.parse(conn, fragment)

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

        message = json.dumps((cmd, args)) + PROTO_TERMINATOR

        poll = select.poll()
        tosend = message

        try:
            self.write_mode(poll, conn)
        except:
            log.error("Error putting conn in write mode.")
            log.error("Interpreting as HUP")
            return select.POLLHUP

        log.debug("Sending: %s" % tosend.replace("\0",""))
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
            if e & select.POLLERR:
                log.debug("Write ERR")
                return select.POLLHUP
            if e & select.POLLOUT:
                try:
                    sent = conn.send(tosend.encode("UTF-8"))
                except Exception as e:
                    if e.args[0] == errno.EINTR:
                        continue
                    log.error("Error sending: %s" % e[1])
                    log.error("Interpreting as HUP")
                    return select.POLLHUP

                tosend = tosend[sent:]
                log.debug("Sent %d bytes." % sent)

    def disconnected(self, conn):
        pass
