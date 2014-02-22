import sys
from distutils.core import setup

if sys.version_info[0] < 3 or sys.version_info[1] < 3:
    sys.exit('Error: Python 3.3 or later required')

setup(name='dircheck',
      version='0.1',
      author="Shane O'Connell",
      author_email='shane@oconnell.cc',
      packages=['dircheck'],
      scripts=['scripts/dircheck']
)
