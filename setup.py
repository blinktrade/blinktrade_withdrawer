#!/usr/bin/env python

from setuptools import setup

version = "0.1"

REQUIREMENTS = [i.strip() for i in open("requirements.txt").readlines()]

setup(
  name="blinktrade_withdrawer",
  version=version,
  author="Rodrigo Souza",
  packages = [
    "blinktrade_withdrawer",
    ],
  entry_points = { 'console_scripts':
                     [
                       'blinktrade_withdrawer = blinktrade_withdrawer.main:main'
                     ]
  },
  install_requires=REQUIREMENTS,
  author_email='r@blinktrade.com',
  url='https://github.com/blinktrade/blinktrade_withdrawer',
  license='http://www.gnu.org/copyleft/gpl.html',
  description='Automatically process blinktrade withdrawal requests'
)
