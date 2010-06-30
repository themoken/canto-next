from distutils.core import setup

setup(name='Canto',
      version='0.8.0',
      description='Next-gen console RSS/Atom reader',
      author='Jack Miller',
      author_email='jack@codezen.org',
      url='http://codezen.org/canto',
      packages=['canto'],
      scripts=['bin/canto-daemon'],
     )
