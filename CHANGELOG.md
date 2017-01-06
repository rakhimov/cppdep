# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/)


## [Unreleased]

## [0.1.0] - 2017-01-05
### Added
- The original ldep '-l|-L' options to print dependencies (#20)
- '-o' to print reports into a file
- Warn about duplicate and redundant includes (#13)
- Extended definition for 'Component' (#7)
- PEP-257 conformance (#2)
- PEP-8 conformance (#1)
- Python 3 support
- PyPI package
- XML configuration example and RNG schema
- Travis CI (Linux, OS X) and AppVeyor CI (Windows) setups

### Changed
- Differentiate 'paths' into source, include, and alias.
- Print warnings to stderr instead of stdout (#12)
- Report Component levels instead of Graph layers (#9)
- Refactor the procedural design into the object-oriented design (#4)
- Change '-f' flag into '-c' flag
- Replace optparse with argparse
- XML configuration file format

### Removed
- Redundant printing a list of cumulative dependencies (#20)
- Indirect missing-header include warnings
- Global cross-package and cross-package-group component dependency analysis
- 'details-of-components/--debug' verbosity
- ``dot2any.py`` helper script
- Manual profiling code (use ``pyvmmonitor`` instead)
- Manual testing code (automated with ``nosetest``)

### Fixed
- Level 0 External components missing from the report and graph (#21)
- Incorrect dependency processing with file basenames (#6)
- Wrong level calculation for cycles (#8)
- Double counting of common components in CCD calculations (#11)
- Missing cycles from the Dot graph (#10)
- Outdated networkx API usage


## [0.0.0] - 2016-09-24
Big Bang: fork https://github.com/yuzhichang/cppdep
