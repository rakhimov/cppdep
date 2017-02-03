#!/usr/bin/env python
"""The setup script to generate dist files for PyPi.

To upload the release to PyPi:
    $ ./setup.py sdist bdist_wheel --universal
    $ twine upload dist/*
"""

from setuptools import setup

from cppdep import cppdep

setup(
    name="cppdep",
    version=cppdep.VERSION,
    maintainer="Olzhas Rakhimov",
    maintainer_email="ol.rakhimov@gmail.com",
    description="Dependency analyzer for C/C++ projects",
    download_url="https://github.com/rakhimov/cppdep",
    license="GPLv3+",
    install_requires=["networkx", "pydotplus", "PyYAML", "PyKwalify>=1.6.0"],
    keywords=["c++", "c", "static analysis", "dependency analysis"],
    url="http://github.com/rakhimov/cppdep",
    packages=["cppdep"],
    package_data={"cppdep": ["config_schema.yml"]},
    entry_points={"console_scripts": ["cppdep = cppdep.__main__:main"]},
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
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5"
    ],
)
