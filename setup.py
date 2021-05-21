#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io
import os
import sys
from shutil import rmtree

from setuptools import find_packages, setup, Command

NAME = 'substrate-utils'
VERSION = '0.1'
DESCRIPTION = ''
URL = 'https://github.com/stakelink/substrate-utils'
EMAIL = 'ops@stakelink.io'
AUTHOR = 'STAKELINK'
REQUIRES_PYTHON = '>=3.6.0'
LICENSE = 'MIT'
REQUIRED = [
    'substrate-interface>=0.13',
    'cachetools'
]

here = os.path.abspath(os.path.dirname(__file__))

with open("README.md", "r", encoding="utf-8") as fh:
    LONG_DESCRIPTION = fh.read()

about = {}
if not VERSION:
    with open(os.path.join(here, NAME, '__version__.py')) as f:
        exec(f.read(), about)
else:
    about['__version__'] = VERSION

setup(
    name=NAME,
    version=about['__version__'],
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author=AUTHOR,
    author_email=EMAIL,
    python_requires=REQUIRES_PYTHON,
    url=URL,
    classifiers=[
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    packages=['substrateutils'],
    entry_points={},
    install_requires=REQUIRED,
    license=LICENSE,
    project_urls={ 
        'Bug Reports': 'https://github.com/stakelink/substrate-utils/issues',
        'Source': 'https://github.com/stakelink/substrate-utils',
    },
)
