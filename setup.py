#!/usr/bin/env python3

from distutils.command.install_data import install_data
from distutils.command.build_py import build_py
from distutils.core import setup
import subprocess
import glob
import os

string_version = "0.9.7"

changes = ['canto_backend.py','remote.py']

class canto_next_build_py(build_py):
    def run(self):
        for source in changes:
            os.utime("canto_next/" + source, None)
        build_py.run(self)

class canto_next_install_data(install_data):
    def run(self):
        try:
            git_hash = subprocess.check_output(["git", "describe"]).decode("UTF-8")[-9:-1]
        except Exception as e:
            print(e)
            git_hash = ""

        install_data.run(self)

        install_cmd = self.get_finalized_command('install')
        libdir = install_cmd.install_lib

        for source in changes:
            with open(libdir + '/canto_next/' + source, 'r+') as f:
                d = f.read().replace("REPLACE_VERSION", "\"" + string_version + "\"")
                d = d.replace("GIT_HASH", "\"" + git_hash + "\"")
                f.truncate(0)
                f.seek(0)
                f.write(d)

setup(name='Canto',
      version=string_version,
      description='Next-gen console RSS/Atom reader',
      author='Jack Miller',
      author_email='jack@codezen.org',
      license='GPLv2',
      url='http://codezen.org/canto-ng',
      download_url='http://codezen.org/static/canto-daemon-' + string_version + '.tar.gz',
      packages=['canto_next'],
      scripts=['bin/canto-daemon','bin/canto-remote'],
      data_files = [("share/man/man1/", ["man/canto-daemon.1", "man/canto-remote.1"]),
                    ("lib/systemd/user", ["systemd/user/canto-daemon.service"]),
                    ("lib/canto/plugins", glob.glob("plugins/*.py"))],
      cmdclass = {  'install_data' : canto_next_install_data,
                    'build_py' : canto_next_build_py },
)
