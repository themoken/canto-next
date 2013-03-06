from distutils.command.install_data import install_data
from distutils.core import setup

numeric_version = [ 0, 8, 2 ]
string_version = ".".join([ str(i) for i in numeric_version])

class canto_next_install_data(install_data):
    def run(self):
        install_data.run(self)

        install_cmd = self.get_finalized_command('install')
        libdir = install_cmd.install_lib

        for source in ['canto_backend.py','remote.py']:
            with open(libdir + '/canto_next/' + source, 'r+') as f:
                d = f.read().replace("REPLACE_WITH_VERSION", "\"" + string_version + "\"")
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
      data_files = [("share/man/man1/", ["man/canto-daemon.1", "man/canto-remote.1"])],
      cmdclass = { 'install_data' : canto_next_install_data },
)
