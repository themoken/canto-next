# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from threading import Thread
import logging
import socket
import select
import errno
import time
import os

PROTO_TERMINATOR='\x00'

log = logging.getLogger('SOCKET')

class CantoSocket:
    def __init__(self, socket_name, **kwargs):
        if "server" in kwargs and kwargs["server"]:
            self.server = True
        else:
            self.server = False

        # Server startup, remove old socket
        if self.server and os.path.exists(socket_name):
            os.remove(socket_name)

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        # Use non-blocking streams
        self.socket.setblocking(0)

        # Setup the socket.
        # For the server, self.socket is made ready for .accept() to
        #   get a read/write socket.
        # For the client, self.socket is read to be read/written to.

        if self.server:
            self.socket.bind(socket_name)
            self.socket.listen(5)
        else:
            tries = 3
            while tries > 0:
                try:
                    self.socket.connect(socket_name)
                    break
                except Exception, e:
                    if e[0] != errno.ECONNREFUSED or tries == 1:
                        raise
                time.sleep(1)
                tries -= 1

        # Holster for partial reads.
        self.fragment = u""

    # Setup poll.poll() object to watch for read status on conn.
    def read_mode(self, poll, conn):
        poll.register(conn.fileno(),\
                select.POLLIN | select.POLLHUP | select.POLLERR)

    # Setup poll.poll() object to watch for write status on conn.
    def write_mode(self, poll, conn):
        poll.register(conn.fileno(),\
                select.POLLOUT | select.POLLHUP | select.POLLERR)


    # Take raw data, return (cmd, args) tuple or None if not enough data.
    def parse(self, data):

        self.fragment += data

        if PROTO_TERMINATOR not in self.fragment:
            return None

        message, self.fragment = self.fragment.split(PROTO_TERMINATOR, 1)

        try:
            cmd, args = message.split(' ', 1)
            log.info("EVAL'd args = %s (%s)" % (eval(args), type(eval(args))))
            return (cmd, eval(args))
        except:
            log.info("Failed to parse message: %s" % message)

    # Reads from a connection, returns:
    # 1) (cmd, args) from self.parse if possible.
    # 2) None, if there was not enough data read.
    # 3) select.POLLHUP if the connection is dead.

    def do_read(self, conn, timeout=None):
        if self.fragment and PROTO_TERMINATOR in self.fragment:
            log.info("retrieving next command from self.fragment")
            return self.parse("") # <- already uses self.fragment

        poll = select.poll()
        self.read_mode(poll, conn)

        # We only care about the first (only) descriptor's event
        try:
            p = poll.poll(timeout)
        except select.error as (err, strerror):
            if err == errno.EINTR:
                return
            raise

        if timeout and not p:
            return

        e = p[0][1]

        log.debug("E: %d" % e)
        if e & select.POLLHUP:
            log.debug("Read HUP")
            return select.POLLHUP
        if e & select.POLLERR:
            log.debug("Read ERR")
            return select.POLLHUP
        if e & select.POLLIN:
            fragment = conn.recv(1024)
            log.debug("Read Buffer: %s" % fragment )
            return self.parse(fragment)

        # Non-empty, but not anything we're interested in?
        log.debug("Unknown poll.poll() return")
        return select.POLLHUP

    # Writes a (cmd, args) to a single connection, returns:
    # 1) None if the write completed.
    # 2) select.POLLHUP is the connection is dead.

    def do_write(self, conn, cmd, args):

        message = cmd + " " + repr(args) + PROTO_TERMINATOR

        poll = select.poll()
        tosend = message
        self.write_mode(poll, conn)

        log.debug("Sending: %s" % tosend)
        while tosend:

            # Again, we only care about the first descriptor's mask
            p = poll.poll()
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
                sent = conn.send(tosend)
                tosend = tosend[sent:]
                log.debug("Sent %d bytes." % sent)
