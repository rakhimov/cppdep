######
cppdep
######

``cppdep.py`` is designed for analyzing dependencies
among components/packages/package groups of a large C/C++ project.
This is a rewrite of dep_utils(adep/cdep/ldep),
which is provided by John Lakos' book "Large-Scale C++ Software Design", Addison Wesley (1996).
The location of ``dep_utils`` source code indicated at the book
is outdated and I only find a copy of it (via Google) at http://www-numi.fnal.gov/computing/d120/releases/R2.2/Dependency/.


Differences to original dep_utils
=================================

- Rewrite in Python. More maintainable.
- Easier to use. Only one simple XML config file need.
  Unified adep/dep/cdep into one.
- Remove file alias support
  since the file name length limitation is much relax the 20 years ago.
- Support multiple package groups and packages
- Support exporting final dependency graph to Graphviz dot format.

The objective of this tool is to detect following cases in source code:

1) Failed to associate some headers/dotC files with any component.

2) File name conflicts.

    2.1) File basename conflicts among our headers.
         For example, libA/List.h and libA/List.hpp, libA/Stack.h and libB/Stack.hpp.

    2.2) File basename conflicts among our dotCs.
         For example, libA/List.cc and libA/List.cpp, libA/Stack.cc and libB/Stack.cpp

    2.3) File name conflicts between our and outside headers.
         For example, libA/map.h and /usr/include/c++/4.4/debug/map.h.

3) Including issues:

    3.1) Some headers included directly or indirectly don't exist.

    3.2) DotC does not depend on its associated header.

    3.3) DotC does not include its associated header directly.

    3.4) DotC does not include its associated header before other headers.

4) Cycle dependencies among components/packages/package groups.

.. note:: A component consists of a pair of one dotH and one dotC,
          and the basenames of them match. For example, (Foo.h, Foo.cpp).

Each of above cases is considered as a quality flaw
and should be removed by revising the code.


Limitation/Bugs:
================

1) Warning 1 results lost dependencies.
2) Warning 2 often results incorrect dependencies,
   especially when those conflict files' context are different.
3) Warning 3.1 indicates a piece of dead code including non-exiting headers.
   If the header does exist at another path,
   you need to add that path into the configuration XML
   in order to get back the lost dependencies.
4) Warning 3.2 often results incorrect dependencies.
5) There are another cases may result lost dependencies.
   For example, [1] a dotC declares global variable or function
   instead of including a header which does the declaration.
   [2] Embedded dynamic dependencies,
   such as dynamic loading and configurable internal services.
6) There are another cases may result incorrect dependencies.
   For example, a piece of dead code of foo.cc includes bar.h,
   and bar.h happens to exist in another package/package group.

************
Requirements
************

#. Python 2.7
#. NetworkX from http://networkx.lanl.gov/.

NetworkX 1.7 and all of its dependencies can be installed using ``apt-get`` as following:

.. code-block:: bash

    $ sudo apt-get install python-networkx

Here's how to convert a Graphviz dot file to PDF format.

.. code-block:: bash

    $ dot -Tpdf graph1.dot -o graph1.pdf


****
TODO
****

- Analyze bottlenecks. "...we consider classes that refer to more than 20 other classes and which are referred to by more than 20 other classes as critical. On the level of subsystems the critical limit is 10 referring and referred to subsystems." -- Klaus Wolfmaier and Rudolf Ramler: Common Findings and Lessons Learned from Software Architecture and Design Analysis, http://metrics2005.di.uniba.it/IndustryTrack/WolfmaierRamler_SoftwareArchitectureDesignAnalysis.pdf

- PEP8 the code.

- Consider OOP design instead of the current procedural.

    * Get rid of non-constant global var.
    * Decoupling for parallelization.

- Write tests.

- Support Python 3.


**************
External links
**************

.. TODO: Remove the mention of commercial tools. This is a GPL project, after all.

1) dependency-analysis is a part of static-code-analysis. There are several commercial products which are able to do dependency-analysis on http://en.wikipedia.org/wiki/List_of_tools_for_static_code_analysis.

2) Here is a discussion on C++ project dependency analysis: http://stackoverflow.com/questions/1137480/visual-c-project-dependency-analysis.

3) Nmdepend is a lightweight 'link-time' dependency analyzer for C++. It uses object files and libraries instead of source-code as input. It runs UNIX and Cygwin. (http://sourceforge.net/projects/nmdepend/).
