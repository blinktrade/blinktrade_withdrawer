#!/usr/bin/env python

from setuptools import setup

version = "0.1"

REQUIREMENTS = [i.strip() for i in open("requirements.txt").readlines()]

setup(
  name="blockchain_info_withdrawer",
  version=version,
  author="Rodrigo Souza",
  packages = [
    "blockchain_info_withdrawer",
    ],
  entry_points = { 'console_scripts':
                     [
                       'blockchain_info_withdrawer = blockchain_info_withdrawer.blockchain_info:main'
                     ]
  },
  install_requires=REQUIREMENTS,
  author_email='r@blinktrade.com',
  url='https://github.com/blinktrade/blockchain_info_withdrawer',
  license='http://www.gnu.org/copyleft/gpl.html',
  description='Automatically process all withdrawal requests using Blockchain.info wallet api'
)
