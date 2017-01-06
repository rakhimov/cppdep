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

``cppdep`` performs dependency analyses
among components/packages/package groups of a large C/C++ project.
This is a rewrite of ``dep_utils(adep/cdep/ldep)``,
which is provided by John Lakos' book
"Large-Scale C++ Software Design", Addison Wesley (1996).

.. |logo| image:: cppdep_small.png


Differences from dep_utils
==========================

- Rewrite in Python, unifying ``adep/cdep/ldep`` into one tool
- Project analysis configuration with an XML file
- No file alias support for the archaic file-name length limitations.
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

#. Python 2.7 / 3.3+
#. `NetworkX <http://networkx.lanl.gov/>`_
#. pydotplus
#. (Optional) `Graphviz <http://www.graphviz.org/>`_
#. (Optional) `xdot <https://github.com/jrfonseca/xdot.py>`_

The dependencies can be installed with ``pip``.

.. code-block:: bash

    $ sudo pip install networkx pydotplus


Installation
============

The latest stable release from PyPi:

.. code-block:: bash

    $ sudo pip install cppdep


Usage
=====

Create an XML configuration file
that describes the project.
``config_example.xml`` and ``config_schema.rng`` are given for guidance.

In the root directory of the project with the configuration file,
run the following command to generate dependency analysis reports and graphs.

.. code-block:: bash

    $ cppdep -c /path/to/config/xml


Graph to Image Conversion
=========================

To view the generated graph dot files without converting to other formats.

.. code-block:: bash

    $ xdot graph.dot

Here's how to convert a Graphviz dot file to PDF format.

.. code-block:: bash

    $ dot -Tpdf graph1.dot -o graph1.pdf

Apply ``-O`` flag to automatically generate output file names from the input file names.

.. code-block:: bash

    $ dot -T pdf graph1.dot -O  # The output file is graph1.dot.pdf

To run ``dot`` on files in directories and sub-directories recursively.

.. code-block:: bash

    $ find -type f -name "*.dot" directory_path | xargs dot -Tpdf -O

To create output file names without ``.dot`` in the name.

.. code-block:: bash

    $ find -type f -name "*.dot" directory_path -exec sh -c 'dot -Tpdf "${0}" -o "${0%.*}.pdf"' {} \;


External links
==============

#. The last known location of John Lakos' ``dep_utils`` source code:
   http://www-numi.fnal.gov/computing/d120/releases/R2.2/Dependency/

#. Experimental packaging of ``dep_utils`` source code:
   https://sourceforge.net/projects/introspector/files/lsc-large-scale-c/first-release/

#. `Nmdepend <http://sourceforge.net/projects/nmdepend/>`_,
   a lightweight 'link-time' dependency analyzer for C++
   using object files and libraries instead of source-code as input.


Acknowledgments
===============

- John Lakos for inventing the analysis and providing ``dep_utils``.
- `Zhichang Yu <https://github.com/yuzhichang>`_ for rewriting ``dep_utils`` into Python.
