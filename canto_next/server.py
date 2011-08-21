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
        self.conn_thread = None
        self.connections = [] # (socket, thread) tuples
        self.alive = True

        self.start_conn_loop()

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

    # Sit and select for connections on sockets:

    def conn_loop(self, sockets):
        try:
            while self.alive:
                r, w, x = select.select(sockets, [], sockets)
                for s in sockets:
                    # If socket is readable, it's got a pending connection.
                    if s in r:
                        conn = s.accept()
                        log.info("conn %s from sock %s" % (conn, s))
                        self.queue.put((conn[0], ("NEWCONN","")))
        except Exception, e:
            tb = traceback.format_exc(e)
            log.error("Connection monitor thread dead on exception:")
            log.error("\n" + "".join(tb))
            return

    def start_conn_loop(self):
        self.conn_thread = Thread(target = self.conn_loop,
                args = (self.sockets,))
        self.conn_thread.daemon = True
        self.conn_thread.start()
        log.debug("Spawned connection monitor thread.")

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

    def accept_conn(self, conn):

        # Notify watchers about new socket.
        call_hook("new_socket", [conn])

        self.connections.append((conn,\
                Thread(target = self.queue_loop,\
                       args = (conn,))
                ))

        self.connections[-1][1].daemon = True
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
