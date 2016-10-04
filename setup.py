import os
from setuptools import setup

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name="cppdep",
    version="0.0.2",
    maintainer='Olzhas Rakhimov',
    maintainer_email="ol.rakhimov@gmail.com",
    description="Dependency analyzer for C/C++ projects",
    download_url="https://github.com/rakhimov/cppdep",
    license="GPLv3",
    install_requires=["networkx", "pydotplus"],
    keywords=["c++", "c", "static analysis", "dependency analysis"],
    url="http://github.com/rakhimov/cppdep",
    packages=[],
    py_modules=["cppdep", "networkx_ext"],
    entry_points={"console_scripts": ["cppdep = cppdep:main"]},
    long_description=read('README.rst'),
    classifiers=[
        "Development Status :: 3 - Alpha",
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
