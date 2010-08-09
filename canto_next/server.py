# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from protocol import CantoSocket

from socket import SHUT_RDWR
from threading import Thread
import logging
import select

log = logging.getLogger("SERVER")

allsockets = []

class CantoServer(CantoSocket):
    def __init__(self, socket_name, queue, testing = False):
        CantoSocket.__init__(self, socket_name, server=True)
        self.queue = queue
        self.testing = testing
        self.connections = [] # (socket, thread) tuples
        self.alive = True

    # Endlessly consume data from the connection. If there's enough data
    # for a complete command, toss it on the shared Queue.Queue

    def queue_loop(self, conn):
        while self.alive:
            d = self.do_read(conn)
            if d:
                if d == select.POLLHUP:
                    log.info("Connection ended.")
                    return 0
                self.queue.put((conn, d))
                if self.testing:
                    break

    # Remove dead connection threads.

    def no_dead_conns(self):
        live_conns = []
        for c, t in self.connections:
            if t.isAlive():
                live_conns.append((c,t))
            else:
                global allsockets
                log.debug("removing socket %s" % c)
                allsockets.remove(c)
                log.debug("allsockets: %s" % allsockets)
                t.join()
        self.connections = live_conns

    # Cleanup dead threads, check for new connections and spawn a new
    # thread if necessary

    def check_conns(self):
        # Dead thread maintenance.
        self.no_dead_conns()

        try:
            conn = self.socket.accept()
        except:
            return # No new connection, we're done.

        log.debug("adding socket %s" % conn[0])
        global allsockets
        allsockets.append(conn[0])
        log.debug("allsockets: %s" % allsockets)

        # New connection == Spawn a queue_loop thread.
        self.connections.append((conn[0],\
                Thread(target = self.queue_loop,\
                args = (conn[0],))))

        self.connections[-1][1].start()
        log.debug("Spawned new thread.")

    # Write a (cmd, args) to a single connection.
    def write(self, conn, cmd, args):
        self.do_write(conn, cmd, args)

    # Write a (cmd, args) to every connection.
    def write_all(self, cmd, args):
        self.no_dead_conns()
        for conn, t in self.connections:
            self.do_write(conn, cmd, args)

    def exit(self):
        self.alive = False
        for conn, t in self.connections:
            conn.shutdown(SHUT_RDWR)
            conn.close()
            t.join()

    # For testing, step through
    def get_one_cmd(self):
        while self.queue.empty():
            self.check_conns()
