#!/usr/bin/env python
"""The setup script to generate dist files for PyPi.

To upload the release to PyPi:
    $ ./setup.py sdist bdist_wheel --universal
    $ twine upload dist/*
"""

from setuptools import setup

import cppdep

setup(
    name="cppdep",
    version=cppdep.VERSION,
    maintainer="Olzhas Rakhimov",
    maintainer_email="ol.rakhimov@gmail.com",
    description="Dependency analyzer for C/C++ projects",
    download_url="https://github.com/rakhimov/cppdep",
    license="GPLv3+",
    install_requires=["networkx", "pydotplus"],
    keywords=["c++", "c", "static analysis", "dependency analysis"],
    url="http://github.com/rakhimov/cppdep",
    packages=[],
    py_modules=["cppdep", "graph"],
    entry_points={"console_scripts": ["cppdep = cppdep:main"]},
    long_description=open("README.rst").read(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: C",
        "Programming Language :: C++",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS :: MacOS X",
        "Environment :: Console",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5"
    ]
)
