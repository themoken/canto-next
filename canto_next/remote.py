# -*- coding: utf-8 -*-
#Canto - RSS reader backend
#   Copyright (C) 2010 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from client import CantoClient
from encoding import encoder, decoder

import sys

class CantoRemote(CantoClient):
    def __init__(self):
        if self.common_args():
            sys.exit(-1)

        self.start_daemon()

        try:
            CantoClient.__init__(self, self.socket_path)
        except Exception, e:
            print "Error: %s" % e
            sys.exit(-1)

        self.handle_args()

    def print_help(self):
        print "USAGE: canto-remote [command] [options]"
        self.print_commands()

    def print_commands(self):
        print "COMMANDS"
        print "\thelp - get help on a command"
        print "\tconfig - change configuration variables"

    def cmd_config(self):
        """USAGE: canto-remote config [option](=value) ...
    Where option is a full variable declaration like 'section.variable' and
    value is any string. If value is omitted, the current value will be printed.
    Any number of options can be printed or set at one time.

    NOTE: validation is done by the client that uses the variable, canto-remote
    will let you give bad values, or even set values to non-existent
    variables."""

        if len(sys.argv) < 3:
            return False

        sets = {}
        gets = []

        for arg in sys.argv[2:]:
            if "=" in arg:
                var, val = arg.split("=", 1)
                setting = True
            else:
                var = arg
                setting = False

            if "." not in var:
                print "ERROR: Unable to parse \"%s\" as section.variable" % var
                continue

            section, secvar = var.split(".", 1)

            if setting:
                if section in sets:
                    sets[section].update({secvar : val})
                else:
                    sets[section] = { secvar : val }

            if var not in gets:
                gets.append(var)

        self.write("SETCONFIGS", sets)
        self.write("CONFIGS", gets)

        r = None
        while True:
            r = self.read()
            if type(r) == int:
                if r == 16:
                    print "Server hung up."
                else:
                    print "Got code: %d" % r
                print "Please check daemon-log for exception."
                return
            elif type(r) == tuple:
                if r[0] == "CONFIGS":
                    break
                continue
            else:
                print "Unknown return: %s" % r
                break

        for section in r[1].keys():
            for secvar in r[1][section].keys():
                print "%s.%s = %s" % (section, secvar, r[1][section][secvar])

        return True

    def cmd_help(self):
        """USAGE: canto-remote help [command]"""
        if len(sys.argv) < 3:
            return False

        command = "cmd_" + sys.argv[2]
        if command in dir(self):
            print getattr(self, command).__doc__
        else:
            print self.cmd_help.__doc__
            self.print_commands()

    def handle_args(self):
        if len(sys.argv) < 2:
            self.print_help()
            return

        sys.argv = [ decoder(a) for a in sys.argv ]

        command = "cmd_" + sys.argv[1]
        if command in dir(self):
            func = getattr(self, command)
            r = func()
            if r == False:
                print func.__doc__
        else:
            self.print_help()
