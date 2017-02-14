# Copyright (C) 2016-2017 Olzhas Rakhimov
# Copyright (C) 2010, 2014 Zhichang Yu
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""C/C++ dependency analyzer.

Physical dependency analyzer
for components/packages/package groups of a large C/C++ project.
"""

from __future__ import absolute_import

import collections
import fnmatch
import glob
import itertools
import logging
import os.path
import re
import sys

from yaml import safe_load
from pykwalify.core import Core as Validator

from .graph import Graph


VERSION = '0.2.2'  # The latest release version.

_SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'config_schema.yml')
assert os.path.isfile(_SCHEMA_FILE), 'The cppdep schema file is missing.'
assert safe_load(open(_SCHEMA_FILE))  # Will throw if invalid.

_FILE_OPEN_FLAGS = {} if sys.version[0] == '2' else {'errors': 'replace'}


# Allowed common abbreviations in the code:
# ccd   - Cumulative Component Dependency (CCD)
# nccd  - Normalized CCD
# accd  - Average CCD
# cd    - component dependency (discouraged abbreviation!)
# pkg   - package (discouraged abbreviation!)
# hfile - header file
# cfile - implementation file
# dep   - dependency (discouraged abbreviation!)


class InvalidArgumentError(Exception):
    """General errors with invalid arguments."""

    pass


class AnalysisError(Exception):
    """The analysis cannot complete due to misconfiguration."""

    pass


def warn(message):
    """Logs a warning message."""
    logging.warn(message)


def strip_ext(filename):
    """Strips the extension from a filename."""
    return os.path.splitext(filename)[0]


def path_normjoin(path, *paths):
    """Returns normalized result of joining of paths."""
    return os.path.normpath(os.path.join(path, *paths))


def path_common(paths):
    """Returns common prefix path for the argument absolute normalized paths."""
    if not paths:
        return ''
    path = os.path.commonprefix(paths)
    assert os.path.isabs(path)
    if path[-1] == os.path.sep:
        return os.path.dirname(path)
    sep_pos = len(path)
    if all(len(x) == sep_pos or x[sep_pos] == os.path.sep for x in paths):
        return path
    return os.path.dirname(path)


def path_isancestor(parent, child):
    """Returns true if the child abspath is a subpath of the parent abspath."""
    if len(parent) > len(child) or not child.startswith(parent):
        return False
    return (len(parent) == len(child) or parent[-1] == os.path.sep or
            child[len(parent)] == os.path.sep)


def path_to_posix_sep(path):
    """Normalize the path separator to Posix (mostly for Windows)."""
    return path.replace('\\', '/') if os.name == 'nt' else path


def yaml_optional(dictionary, element, default_value):
    """Retrieves optional element values with defaults."""
    return dictionary[element] if element in dictionary else default_value


def yaml_optional_list(dictionary, element):
    """Retrieves optional list values with an empty list as default."""
    return yaml_optional(dictionary, element, [])


class Include(object):
    """Representation of an include directive.

    Attributes:
        with_quotes: True if the include is within quotes ("")
            instead of angle brackets (<>).
        hfile: The normalized path to the header file in the directive.
        hpath: The absolute path to the header file.
    """

    _RE_INCLUDE = re.compile(r'^\s*#\s*include\s*'
                             r'(<(?P<brackets>\S+?)>|"(?P<quotes>\S+?)")')

    __slots__ = ['__include_path', 'hfile', 'with_quotes', 'hpath']

    def __init__(self, include_path, with_quotes):
        """Initializes with attributes.

        Args:
            include_path: The original path in the include directive.
            with_quotes: True if the path is within quotes instead of brackets.
        """
        self.__include_path = include_path
        self.hfile = os.path.normpath(include_path)
        self.with_quotes = with_quotes
        self.hpath = None

    def __str__(self):
        """Produces the original include with quotes or brackets."""
        if self.with_quotes:
            return '"%s"' % self.__include_path
        return '<%s>' % self.__include_path

    def __hash__(self):
        """To work with sets."""
        return hash(self.hfile)

    def __eq__(self, other):
        """Assumes the same working directory and search paths."""
        return self.hfile == other.hfile

    def __ne__(self, other):
        """Assumes the same working directory and search paths."""
        return not self == other

    @staticmethod
    def grep(file_path):
        """Processes include directives in a source file.

        Args:
            file_path: The full path to the source file.

        Yields:
            Include objects constructed with the directives.
        """
        with open(file_path, **_FILE_OPEN_FLAGS) as src_file:
            for line in src_file:
                include = Include._RE_INCLUDE.search(line)
                if not include:
                    continue
                if include.group("brackets"):
                    yield Include(include.group("brackets"), with_quotes=False)
                else:
                    yield Include(include.group("quotes"), with_quotes=True)

    def locate(self, cwd, include_dirs, include_patterns):
        """Locates the included header file path.

        All input directory paths must be absolute.

        Args:
            cwd: The working directory for source file processing.
            include_dirs: The directories to search for the file,
                ordered from internal to external/system directories.
            include_patterns: (package, [regex]) to search with patterns.

        Returns:
            (hpath, package) with None indicating failure to find the file.
        """
        assert self.hpath is None

        def _find_in(include_dir):
            """Returns True if the path is found."""
            file_hpath = path_normjoin(include_dir, self.hfile)
            if os.path.isfile(file_hpath):
                self.hpath = file_hpath
                return True
            return False

        if self.with_quotes and _find_in(cwd):
            return self.hpath, None

        for package, patterns in include_patterns:
            if any(x.match(self.hfile) for x in patterns):
                return self.hfile, package

        if any(_find_in(x) for x in
               (iter if self.with_quotes else reversed)(include_dirs)):
            return self.hpath, None

        return None, None


class Component(object):
    """Representation of a component in a package.

    Attributes:
        name: A unique name within the package.
        hpath: The absolute path to the header file.
        cpath: The absolute path to the implementation file.
        package: The package this component belongs to.
        working_dir: The parent directory.
        dep_components: Dependency components.
        includes_in_h: Include directives in the header file.
        includes_in_c: Include directives in the implementation file.
    """

    def __init__(self, hpath, cpath, package):
        """Initialization of a free-standing component.

        Warns about incomplete components.

        Args:
            hpath: The path to the header file of the component.
            cpath: The path to the implementation file of the component.
            package: The package this components belongs to.
        """
        assert hpath or cpath
        self.name = path_to_posix_sep(
            strip_ext(os.path.relpath(cpath or hpath, package.root)))
        if not hpath:
            warn('incomplete component: missing header: %s in %s.%s' %
                 (self.name, package.group.name, package.name))
        self.hpath = hpath
        self.cpath = cpath
        self.package = package
        self.working_dir = os.path.dirname(cpath or hpath)
        self.dep_components = set()
        self.includes_in_h = set() if not hpath else list(Include.grep(hpath))
        self.includes_in_c = set() if not cpath else list(Include.grep(cpath))
        self.__sanitize_includes()

    def __str__(self):
        """For printing graph nodes."""
        return self.name

    def dependencies(self):
        """Returns dependency components."""
        return self.dep_components

    def __sanitize_includes(self):
        """Sanitizes and checks includes."""
        def _check_duplicates(path, includes):
            unique_includes = set()
            for include in includes:
                if include in unique_includes:
                    warn('include issues: duplicate include: '
                         '%s in %s' % (str(include), path))
                else:
                    unique_includes.add(include)
            return unique_includes

        def _remove_duplicates():
            if self.hpath:
                self.includes_in_h = _check_duplicates(self.hpath,
                                                       self.includes_in_h)
            if self.cpath:
                self.includes_in_c = _check_duplicates(self.cpath,
                                                       self.includes_in_c)

        def _remove_redundant():
            for include in self.includes_in_c:
                if include in self.includes_in_h:
                    warn('include issues: redundant include: '
                         '%s in %s' % (str(include), self.cpath))
            self.includes_in_c.difference_update(self.includes_in_h)

        if self.hpath and self.cpath:
            hfile = os.path.basename(self.hpath)
            if hfile not in (os.path.basename(x.hfile)
                             for x in self.includes_in_c):
                warn('include issues: missing include: '
                     '%s does not include %s.' % (self.cpath, hfile))
            elif hfile != os.path.basename(self.includes_in_c[0].hfile):
                warn('include issues: include order: '
                     '%s should be the first include in %s.' %
                     (hfile, self.cpath))
        _remove_duplicates()
        _remove_redundant()


class ExternalComponent(object):
    """Representation of an external component.

    Note that external components are degenerate.
    There's no need to acquire full information about their dependencies.

    Attributes:
        hpath: A path to the component header as an identifier.
        package: The package.
    """

    __slots__ = ['hpath', 'package']

    def __init__(self, hpath, package):
        """Constructs an external component with its attributes."""
        self.hpath = hpath
        self.package = package


class Package(object):
    """A collection of components.

    Attributes:
        name: The unique identifier name of the package within its group.
        src_paths: The absolute directory paths the package source components.
        include_paths: The export paths of the package headers.
        alias_paths: The absolute directory paths aliasing to this package.
        group: The package group this package belongs to.
        root: The common root path for all the paths in the package.
        components: The list of unique components in this package.
    """

    _RE_SRC = re.compile(r'(?i)[\w\-]+((?P<h>(\.h(h|xx|\+\+|pp)?)?)|'
                         r'(?P<c>\.((c(c|xx|\+\+|pp)?)|ipp)))$')

    def __init__(self, name, group, src_paths, include_paths, alias_paths,
                 include_patterns, ignore_paths):
        """Constructs an empty package.

        Registers the package in the package group.
        The argument paths are relative to the package group directory.

        Args:
            name: A unique identifier within the package group.
            group: The package group.
            src_paths: The source directory paths (glob patterns).
            include_paths: The export header paths (also alias paths).
            alias_paths: Additional directory paths aliasing to the package.
            include_patterns: Regex pattern strings for include directives.
            ignore_paths: Exlusion paths from the source (glob patterns).

        Raises:
            InvalidArgumentError: Issues with the argument directory paths.
        """
        self.name = name
        self.group = group
        self.src_paths = set()
        self.include_paths = set()
        self.ignore_paths = set()
        self.alias_paths = set()
        self.include_patterns = include_patterns
        self.__init_paths(src_paths, include_paths, alias_paths, ignore_paths)
        self.root = path_common(self.src_paths)
        self.components = []
        self.__dep_packages = None  # set of dependency packages
        group.add_package(self)

    def __str__(self):
        """For printing graph nodes."""
        return self.name

    def __init_paths(self, src_paths, include_paths, alias_paths, ignore_paths):
        """Initializes package paths."""
        def _update(path_container, arg_paths, check_dir=True):
            for path in arg_paths:
                path = os.path.normpath(path)
                abs_path = path_normjoin(self.group.path, path)
                if (check_dir and not os.path.isdir(abs_path) or
                        not abs_path.startswith(self.group.path)):
                    raise InvalidArgumentError(
                        '%s is not a directory in %s (group %s).' %
                        (path, self.group.path, self.group.name))
                if abs_path in path_container:
                    raise InvalidArgumentError('%s is duplicated in %s.%s' %
                                               (abs_path, self.group.name,
                                                self.name))
                path_container.add(abs_path)

        _update(self.src_paths, src_paths, check_dir=False)
        _update(self.ignore_paths, ignore_paths, check_dir=False)
        _update(self.include_paths, include_paths)
        _update(self.alias_paths, alias_paths)
        self.alias_paths.update(self.include_paths)

    def construct_components(self):
        """Traverses the package paths and constructs package components.

        Even though John Lakos defined a component as a pair of h and c files,
        C++ can have template only components
        residing only in header files (e.g., STL/Boost/etc.).
        Moreover, some header-only components
        may contain only inline functions or macros
        without any need for an implementation file
        (e.g., inline math, Boost PPL).
        For these reasons, unpaired header files
        are counted as components by default.

        Unpaired c files are counted as incomplete components with warnings.
        """
        file_type = collections.namedtuple('File', ['rev_path', 'path'])
        hpaths = collections.defaultdict(list)
        cpaths = collections.defaultdict(list)

        # This approach is pessimistic with O(N*logN) instead of O(N)
        # because it assumes the header and implementation files
        # are likely to be in different directories.
        def _reverse(path):
            path = strip_ext(path).split(os.path.sep)
            path.reverse()
            return path

        def _select_src_file(root, filename):
            full_path = os.path.join(root, filename)
            if any(fnmatch.fnmatch(full_path, x) for x in self.ignore_paths):
                return
            src_match = Package._RE_SRC.match(filename)
            if src_match:
                (hpaths if src_match.group('h')
                 else cpaths)[strip_ext(filename)].append(
                     file_type(_reverse(full_path), full_path))

        def _gather_files(dir_path):
            for root, _, files in os.walk(dir_path):
                if any(fnmatch.fnmatch(root, x) for x in self.ignore_paths):
                    continue
                for filename in files:
                    _select_src_file(root, filename)

        for glob_path in self.src_paths:
            for src_path in glob.iglob(glob_path):
                if os.path.isdir(src_path):
                    _gather_files(src_path)
                else:
                    _select_src_file(*os.path.split(src_path))

        self.__pair_files(hpaths, cpaths)

    def __pair_files(self, hpaths, cpaths):
        """Pairs header and implementation files into components."""
        # This should probably be solved with a graph algorithm.
        # Find the nodes with the longest matching consecutive ancestors
        # starting from the node (not the root!).
        # The nodes represent the file and directory names.
        #
        # The association is indeterminate or ambiguous
        # if multiple nodes share the same common ancestors of the same number.
        # Therefore, the algorithm to find
        # the lowest common ancestor seems to lead to false answers.
        def _num_consecutive_ancestors(file_one, file_two):
            return sum(1 for _ in itertools.takewhile(lambda x: x[0] == x[1],
                                                      zip(file_one.rev_path,
                                                          file_two.rev_path)))

        def _pair(hfiles, cfiles):
            assert hfiles and cfiles  # Expected to have few elements.
            candidates = [(x, sorted(((_num_consecutive_ancestors(x, y), y)
                                      for y in hfiles), reverse=True))
                          for x in cfiles]
            candidates.sort(reverse=True,
                            key=lambda x: tuple(y for y, _ in x[1]))
            for cfile, hfile_candidates in candidates:
                for _, hfile in hfile_candidates:
                    if hfile in hfiles:
                        yield hfile.path, cfile.path
                        hfiles.remove(hfile)
                        break
                else:
                    yield None, cfile.path

            for hfile in hfiles:
                yield hfile.path, None

        for filename, hfiles in hpaths.items():
            if filename not in cpaths:
                self.components.extend(
                    Component(x.path, None, self) for x in hfiles)
            else:
                cfiles = cpaths[filename]
                del cpaths[filename]
                self.components.extend(
                    Component(x, y, self) for x, y in _pair(hfiles, cfiles))

        for cfiles in cpaths.values():
            self.components.extend(
                Component(None, x.path, self) for x in cfiles)

    def dependencies(self):
        """Returns dependency packages."""
        if self.__dep_packages is None:
            self.__dep_packages = set()
            for component in self.components:
                self.__dep_packages.update(x.package
                                           for x in component.dependencies()
                                           if x.package != self)
        return self.__dep_packages


class PackageGroup(object):
    """A collection of packages.

    Attributes:
        name: The unique name of the package group.
        path: The absolute path to the group directory.
        packages: {package_name: package} belonging to this group.
    """

    def __init__(self, name, path):
        """Constructs an empty group.

        Args:
            name: A unique global identifier.
            path: The directory path to the group.

        Raises:
            InvalidArgumentError: The path is not a directory.
        """
        if not os.path.isdir(path):
            raise InvalidArgumentError('%s is not a directory.' % path)
        self.name = name
        self.path = os.path.abspath(os.path.normpath(path))
        self.packages = {}
        self.__dep_groups = None  # set of dependency groups

    def __str__(self):
        """For printing graph nodes."""
        return self.name

    def dependencies(self):
        """Returns dependency package groups."""
        if self.__dep_groups is None:
            self.__dep_groups = set()
            for package in self.packages.values():
                self.__dep_groups.update(x.group for x in package.dependencies()
                                         if x.group != self)
        return self.__dep_groups

    def add_package(self, package):
        """Adds a package into the group.

        This function is automatically called in the package constructor.

        Args:
            package: The constructed package.

        Raises:
            InvalidArgumentError: Duplicate package.
        """
        if package.name in self.packages:
            raise InvalidArgumentError(
                '%s is a duplicate package in %s group.' %
                (package.name, self.name))
        self.packages[package.name] = package


class DependencyAnalysis(object):
    """Analysis of dependencies with package groups/packages/components.

    Attributes:
        config: The configuration dictionary.
        external_groups: External dependency packages and package groups.
              {group_name: PackageGroup}
        internal_groups: The package groups of the project under analysis.
              {group_name: PackageGroup}
        include_dirs: Directories to search for included headers.
            It is ordered,
            starting from internal and ending with external directories.
    """

    def __init__(self, config_file):
        """Initializes analysis containers.

        Args:
            config_file: The path to the configuration file.

        Raises:
            YAMLError: Errors loading yaml files.
            SchemaError: The config file is malformed or invalid.
            InvalidArgumentError: The configuration has is invalid values.
        """
        self.config = None
        self.external_groups = {}
        self.internal_groups = {}
        self.include_dirs = []
        self._external_components = {}  # {hpath: ExternalComponent}
        self._internal_components = {}  # {hpath: Component}
        self.__package_aliases = []  # Sorted [(alias_path, external_package)]
        self.__include_patterns = []  # [(package, [regex])]
        self.__parse_config(config_file)
        self.__gather_include_dirs()
        self.__gather_aliases()
        self.__gather_include_patterns()
        self.make_components()

    def __parse_config(self, config_file_path):
        """Parses the configuration file.

        Args:
            config_file_path: The path to the configuration file.

        Raises:
            YAMLError: Errors loading yaml files.
            SchemaError: The configuration file is malformed or invalid.
            InvalidArgumentError: The configuration has invalid values.
        """
        # Load before validation to check for well-formed YAML.
        with open(config_file_path) as config_file:
            self.config = safe_load(config_file)
        Validator(config_file_path, [_SCHEMA_FILE]).validate()

        for pkg_group_config in self.config['internal']:
            DependencyAnalysis.__add_package_group(pkg_group_config,
                                                   self.internal_groups)
        for pkg_group_config in yaml_optional_list(self.config, 'external'):
            DependencyAnalysis.__add_package_group(pkg_group_config,
                                                   self.external_groups)

    @staticmethod
    def __add_package_group(pkg_group_config, pkg_groups):
        """Initializes and adds a package group from configuration.

        Args:
            pkg_group_config: The package-group configuration dictionary.
            pkg_groups: The destination dictionary for member packages.

        Raises:
            InvalidArgumentError: Invalid configuration.
        """
        group_name = pkg_group_config['name']
        group_path = pkg_group_config['path']
        if group_name in pkg_groups:
            raise InvalidArgumentError('Redefinition of %s group' % group_name)

        package_group = PackageGroup(group_name, group_path)

        for pkg_config in pkg_group_config['packages']:
            Package(pkg_config['name'],
                    package_group,
                    yaml_optional_list(pkg_config, 'src'),
                    yaml_optional_list(pkg_config, 'include'),
                    yaml_optional_list(pkg_config, 'alias'),
                    yaml_optional_list(pkg_config, 'pattern'),
                    yaml_optional_list(pkg_config, 'ignore'))

        pkg_groups[group_name] = package_group

    def __gather_include_dirs(self):
        """Gathers include directories from packages."""
        def _add_from(groups):
            for group in groups.values():
                for package in group.packages.values():
                    self.include_dirs.extend(package.include_paths)
        _add_from(self.internal_groups)
        _add_from(self.external_groups)

    def __gather_aliases(self):
        """Gathers aliases for *external* packages lazy include search."""
        for group in self.external_groups.values():
            for package in group.packages.values():
                self.__package_aliases.extend((x, package)
                                              for x in package.alias_paths)
        self.__package_aliases.sort()
        assert (len(set(x for x, _ in self.__package_aliases)) ==
                len(self.__package_aliases)), "Ambiguous aliases to packages"

    def __gather_include_patterns(self):
        """Gathers and compiles include patterns into regex objects."""
        for group in self.external_groups.values():
            for package in group.packages.values():
                self.__include_patterns.append(
                    (package,
                     [re.compile(x) for x in package.include_patterns]))

    def locate(self, include, component):
        """Locates the dependency component.

        Args:
            include: The include object representing the directive.
            component: The dependent component.

        Returns:
            True if the include is found.

        Raises:
            AnalysisError: Failure to associate a header to a component.
        """
        def _find_external_package(hpath):
            for path, package in reversed(self.__package_aliases):
                if path_isancestor(path, hpath):
                    return package
            raise AnalysisError('include error: Cannot associate '
                                '%s file with any component.' % hpath)

        hpath, package = include.locate(component.working_dir,
                                        self.include_dirs,
                                        self.__include_patterns)

        if hpath is None:
            return False
        if package is None and hpath in self._internal_components:
            dep_component = self._internal_components[hpath]
            if dep_component != component:
                component.dep_components.add(dep_component)
        else:
            if hpath in self._external_components:
                component.dep_components.add(
                    self._external_components[hpath])
            else:
                dep_component = ExternalComponent(
                    hpath, package or _find_external_package(hpath))
                component.dep_components.add(dep_component)
                self._external_components[hpath] = dep_component
        return True

    @property
    def internal_components(self):
        """Yields components in internal groups."""
        for group in self.internal_groups.values():
            for package in group.packages.values():
                for component in package.components:
                    yield component

    def make_components(self):
        """Pairs hfiles and cfiles.

        Raises:
            AnalysisError: Misconfiguration or failure of the analysis.
        """
        for group in self.internal_groups.values():
            for package in group.packages.values():
                package.construct_components()

        for component in self.internal_components:
            id_path = component.hpath or component.cpath
            self._internal_components[id_path] = component
            if component.cpath and component.cpath.endswith('.ipp'):
                self._internal_components[component.cpath] = component

        for component in self.internal_components:
            for include in itertools.chain(component.includes_in_h,
                                           component.includes_in_c):
                if not self.locate(include, component):
                    warn('include issues: header not found: %s' % str(include))

    def analyze(self, printer, args):
        """Runs the analysis."""
        def _analyze(graph_name, digraph):
            digraph.analyze()
            digraph.print_cycles(printer)
            if not args.l and not args.L:
                digraph.print_levels(printer)
            else:
                digraph.print_levels(printer, args.l)
            digraph.print_summary(printer)
            digraph.write_dot(graph_name)

        if len(self.internal_groups) > 1:
            printer('\n' + '#' * 80)
            printer('analyzing dependencies among all package groups ...')
            _analyze('system',
                     Graph(self.internal_groups.values(), iter,
                           lambda x: x.name in self.external_groups))

        for group_name, package_group in self.internal_groups.items():
            if len(package_group.packages) > 1:
                printer('\n' + '#' * 80)
                printer('analyzing dependencies among packages in '
                        'the specified package group %s ...' % group_name)
                _analyze(group_name,
                         Graph(package_group.packages.values(),
                               lambda x: (i if i.group == package_group
                                          else i.group for i in x),
                               lambda x: isinstance(x, PackageGroup)))

        for group_name, package_group in self.internal_groups.items():
            for pkg_name, package in package_group.packages.items():
                if not package.components:
                    assert not package.src_paths
                    continue
                printer('\n' + '#' * 80)
                printer('analyzing dependencies among components in '
                        'the specified package %s.%s ...' %
                        (group_name, pkg_name))
                _analyze('_'.join((group_name, pkg_name)),
                         Graph(package.components,
                               lambda x: (i if i.package == package
                                          else i.package for i in x),
                               lambda x: isinstance(x, Package)))
