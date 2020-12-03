# -*- coding: utf-8 -*-

#Canto - RSS reader backend
#   Copyright (C) 2016 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from .protocol import CantoSocket
from .hooks import call_hook

from socket import SHUT_RDWR
from threading import Thread, Lock
import traceback
import logging
import select

log = logging.getLogger("SERVER")

class CantoServer(CantoSocket):
    def __init__(self, socket_name, dispatch, **kwargs):
        kwargs["server"] = True
        CantoSocket.__init__(self, socket_name, **kwargs)
        self.dispatch = dispatch
        self.conn_thread = None

        self.connections_lock = Lock()
        self.connections = [] # (socket, thread) tuples
        self.alive = True

        self.start_conn_loop()

    # Endlessly consume data from the connection. If there's enough data
    # for a complete command, toss it on the shared Queue.Queue

    def read_loop(self, conn):
        try:
            while self.alive:
                d = self.do_read(conn)
                if d:
                    if d == select.POLLHUP:
                        log.info("Connection ended.")
                        return
                    self.dispatch(conn, d)
        except Exception as e:
            tb = traceback.format_exc()
            log.error("Response thread dead on exception:")
            log.error("\n" + "".join(tb))
            return

    # Sit and select for connections on sockets:

    def conn_loop(self, sockets):
        while self.alive:
            try:
                # select with a timeout so we can check we're still alive
                r, w, x = select.select(sockets, [], sockets, 1)
                for s in sockets:
                    # If socket is readable, it's got a pending connection.
                    if s in r:
                        conn = s.accept()
                        log.info("conn %s from sock %s" % (conn, s))
                        self.accept_conn(conn[0])
            except Exception as e:
                tb = traceback.format_exc()
                log.error("Connection monitor exception:")
                log.error("\n" + "".join(tb))
                log.error("Attempting to continue.")

    def start_conn_loop(self):
        self.conn_thread = Thread(target = self.conn_loop,
                args = (self.sockets,), name = "Connection Monitor")
        self.conn_thread.daemon = True
        self.conn_thread.start()
        log.debug("Spawned connection monitor thread.")

    # Remove dead connection threads.

    def no_dead_conns(self):
        self.connections_lock.acquire()
        for c, t in self.connections[:]:
            if not t.is_alive():
                call_hook("server_kill_socket", [c])
                t.join()
                c.close()
                self.connections.remove((c, t))
                if self.connections == []:
                    call_hook("server_no_connections", [])
        self.connections_lock.release()

    def accept_conn(self, conn):
        self.read_locks[conn] = Lock()
        self.write_locks[conn] = Lock()
        self.write_frags[conn] = None

        # Notify watchers about new socket.
        call_hook("server_new_socket", [conn])

        self.connections_lock.acquire()

        self.connections.append((conn,\
                Thread(target = self.read_loop,\
                       args = (conn,), name="Connection #%s" %\
                       (len(self.connections)))
                ))

        self.connections[-1][1].daemon = True
        self.connections[-1][1].start()

        if len(self.connections) == 1:
            call_hook("server_first_connection", [])

        self.connections_lock.release()

        log.debug("Spawned new thread.")

    # Write a (cmd, args) to a single connection.
    def write(self, conn, cmd, args):
        if not conn:
            return None
        return self.do_write(conn, cmd, args)

    # Write a (cmd, args) to every connection.
    def write_all(self, cmd, args):
        self.no_dead_conns()

        self.connections_lock.acquire()
        for conn, t in self.connections:
            self.do_write(conn, cmd, args)
        self.connections_lock.release()

    def exit(self):
        self.alive = False
        self.conn_thread.join()

        # No locking, as we should already be single-threaded

        for conn, t in self.connections:
            conn.shutdown(SHUT_RDWR)
            conn.close()
