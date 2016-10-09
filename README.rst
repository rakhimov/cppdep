######
cppdep
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


Differences from dep_utils
==========================

- Rewrite in Python, unifying ``adep/cdep/ldep`` into one tool.
- Project analysis configuration with an XML file.
- Remove file alias support
  since the file name length limitation is much more relaxed than it was 20 years ago.
- Support for multiple package groups and packages
- Support for exporting final dependency graph to Graphviz dot format.


Analysis Warnings
=================

.. note:: A component (ideally) consists of a pair of one dotH and one dotC
          with the same basename, e.g., ``foo.h`` and ``foo.cpp``.

Each of the following cases may be considered a quality flaw.

1. Failure to associate some header/implementation files with any component,
   leading to lost dependencies.

2. File name conflicts.

    1. File basename conflicts among internal headers.
       For example, libA/List.h and libA/List.hpp, libA/Stack.h and libB/Stack.hpp.
    2. File basename conflicts among internal implementation files.
       For example, libA/List.cc and libA/List.cpp, libA/Stack.cc and libB/Stack.cpp
    3. File name conflicts between internal and external headers.
       For example, libA/map.h and /usr/include/c++/4.4/debug/map.h.

.. note:: This objective and initial implementation is dropped
          for being unnecessary and out-of-scope of the tool.
          It is dubious to qualify "non-conflicting" components
          with the same name but under different packages
          as a quality flaw.
          The separation of projects into packages/modules/folders/namespaces
          is exactly intended to free the developer
          from coming up with quirky names for components.
          It is the most common and best practice to include
          external component or package headers via ``<package/folder/header>``.
          For example, each project, library, package can have its own ``config.h``,
          and to consider it a quality flaw is unjustifiable.

.. note:: It is very rare and unlikely to see file basename conflicts among
          headers and implementation files.
          Codebases suffering from such silly issues
          can leverage system tools to find the conflicts.


.. code-block:: bash

    $ # An example solution for 2.1) and 2.2) with system tools.
    $ find -type f -regextype egrep -regex ".+\.c(c|pp|\+\+)?" -exec sh -c 'echo ${0%.*}' {} \; | sort | uniq -d


3. ``#include`` issues:

    1. Some headers included directly or indirectly don't exist.
       The path to the dependencies may be missing from the XML configuration file.
    2. DotC does not depend on its associated header,
       resulting in incorrect dependencies.
    3. DotC does not include its associated header directly.
    4. DotC does not include its associated header before other headers.

4. Cyclic dependencies among components/packages/package groups.


Limitations
===========

- Indirect `extern` declarations of global variables or functions
  instead of including the proper component header with the declarations.
- Embedded dynamic dependencies,
  such as dynamic loading and configurable internal services.
- Preprocessing or macro expansion is not performed.
  Dependency inclusion via preprocessor *meta-programming* is not handled.


Requirements
============

#. Python 2.7 / 3.3+
#. `NetworkX <http://networkx.lanl.gov/>`_
#. pydotplus
#. (Optional) `Graphviz <http://www.graphviz.org/>`_

The dependencies can be installed with ``pip``.

.. code-block:: bash

    $ sudo pip install networkx pydotplus


Graph to Image Conversion with Graphviz
=======================================

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

#. `The discussion on C++ project dependency analysis <http://stackoverflow.com/questions/1137480/visual-c-project-dependency-analysis>`_

#. `Nmdepend <http://sourceforge.net/projects/nmdepend/>`_,
   a lightweight 'link-time' dependency analyzer for C++
   using object files and libraries instead of source-code as input.


Acknowledgments
===============

- John Lakos for inventing the analysis and providing ``dep_utils``.
- `Zhichang Yu <https://github.com/yuzhichang>`_ for rewriting ``dep_utils`` into Python.
