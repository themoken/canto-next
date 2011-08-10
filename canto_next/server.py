# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from protocol import CantoSocket
from hooks import call_hook

from socket import SHUT_RDWR
from threading import Thread
import traceback
import logging
import select

log = logging.getLogger("SERVER")

class CantoServer(CantoSocket):
    def __init__(self, socket_name, queue, **kwargs):
        kwargs["server"] = True
        CantoSocket.__init__(self, socket_name, **kwargs)
        self.queue = queue
        self.connections = [] # (socket, thread) tuples
        self.alive = True

    # Endlessly consume data from the connection. If there's enough data
    # for a complete command, toss it on the shared Queue.Queue

    def queue_loop(self, conn):
        try:
            while self.alive:
                d = self.do_read(conn)
                if d:
                    if d == select.POLLHUP:
                        log.info("Connection ended.")
                        return
                    self.queue.put((conn, d))
        except Exception, e:
            tb = traceback.format_exc(e)
            log.error("Response thread dead on exception:")
            log.error("\n" + "".join(tb))
            return

    # Remove dead connection threads.

    def no_dead_conns(self):
        live_conns = []
        for c, t in self.connections:
            if t.isAlive():
                live_conns.append((c,t))
            else:
                # Notify watchers about dead socket.
                call_hook("kill_socket", [c])
                t.join()
        self.connections = live_conns

    # Cleanup dead threads, check for new connections and spawn a new
    # thread if necessary

    def check_conns(self):
        # Dead thread maintenance.
        self.no_dead_conns()

        # Try all sockets for new connections.

        conn = None
        for sock in self.sockets:
            try:
                conn = sock.accept()
                log.info("conn %s from sock %s" % (conn, sock))
            except:
                continue # No new connection, try next

        # No sockets had connections, we're done.
        if not conn:
            return

        # Notify watchers about new socket.
        call_hook("new_socket", [conn[0]])

        # New connection == Spawn a queue_loop thread.
        self.connections.append((conn[0],\
                Thread(target = self.queue_loop,\
                args = (conn[0],))))

        self.connections[-1][1].start()
        log.debug("Spawned new thread.")

    # Write a (cmd, args) to a single connection.
    def write(self, conn, cmd, args):
        return self.do_write(conn, cmd, args)

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
