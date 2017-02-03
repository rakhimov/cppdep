######
|logo|
######

.. image:: https://travis-ci.org/rakhimov/cppdep.svg?branch=master
    :target: https://travis-ci.org/rakhimov/cppdep
.. image:: https://ci.appveyor.com/api/projects/status/1ff39sfjp7ija3j8/branch/master?svg=true
    :target: https://ci.appveyor.com/project/rakhimov/cppdep/branch/master
    :alt: 'Build status'
.. image:: https://codecov.io/gh/rakhimov/cppdep/branch/master/graph/badge.svg
  :target: https://codecov.io/gh/rakhimov/cppdep
.. image:: https://landscape.io/github/rakhimov/cppdep/master/landscape.svg?style=flat
   :target: https://landscape.io/github/rakhimov/cppdep/master
   :alt: Code Health
.. image:: https://badge.fury.io/py/cppdep.svg
    :target: https://badge.fury.io/py/cppdep

|

``cppdep`` performs dependency analysis
among components/packages/package groups of a large C/C++ project.
This is a rewrite of ``dep_utils(adep/cdep/ldep)``,
which is provided by John Lakos' book
"Large-Scale C++ Software Design", Addison Wesley (1996).

.. |logo| image:: logo.png


Differences from dep_utils
==========================

- Rewrite in Python, unifying ``adep/cdep/ldep`` into one tool
- Single configuration file (``yaml`` file)
- No file alias support for the archaic file-name length limitations
- An extended notion of Component (header- or source-only)
- Support for multiple packages and package groups
- Support for exporting final dependency graph to Graphviz dot format


Limitations
===========

- Indirect `extern` declarations of global variables or functions
  instead of including the proper component header with the declarations.
- Embedded dynamic dependencies,
  such as dynamic loading and configurable internal services.
- Preprocessing or macro expansion is not performed.
  Dependency inclusion via preprocessor *meta-programming* is not handled.
- Dependency exclusion with C style multi-line comments or macros
  is not respected.


Requirements
============

#. Python 2.7 or 3.4+
#. `NetworkX <http://networkx.lanl.gov/>`_
#. pydotplus
#. PyYAML
#. PyKwalify 1.6.0+

The dependencies can be installed with ``pip``.

.. code-block:: bash

    $ sudo pip install -r requirements.txt


Installation
============

From the source:

.. code-block:: bash

    $ ./setup.py install

The latest stable release from PyPi:

.. code-block:: bash

    $ pip install cppdep


Usage
=====

Create a configuration file
that describes the project for analysis.
``config_schema.yml`` is given for guidance.

In the root directory of the project with the configuration file,
run the following command to generate dependency analysis reports and graphs.

.. code-block:: bash

    $ cppdep -c /path/to/config/file

More documentation and example configurations
can be found in project `wiki <https://github.com/rakhimov/cppdep/wiki>`_.


Acknowledgments
===============

- John Lakos for inventing the analysis and providing ``dep_utils``.
- `Zhichang Yu <https://github.com/yuzhichang>`_ for rewriting ``dep_utils`` into Python.
