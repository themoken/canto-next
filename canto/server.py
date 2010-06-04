# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from protocol import CantoSocket

from threading import Thread
import logging
import select

log = logging.getLogger("SERVER")

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

        # New connection == Spawn a queue_loop thread.
        self.connections.append((conn[0],\
                Thread(target = self.queue_loop,\
                args = (conn[0],))))

        self.connections[-1][1].start()
        log.debug("Spawning new thread.")

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

    # For testing, step through
    def get_one_cmd(self):
        while self.queue.empty():
            self.check_conns()
