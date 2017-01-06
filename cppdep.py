#!/usr/bin/env python
#
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

from __future__ import print_function, division, absolute_import

import argparse as ap
import itertools
import logging
import os.path
import re
import sys
from xml.etree import ElementTree

from graph import Graph


VERSION = '0.1.0'  # The latest release version.

# Allowed common abbreviations in the code:
# ccd   - Cumulative Component Dependency (CCD)
# nccd  - Normalized CCD
# accd  - Average CCD
# cd    - component dependency (discouraged abbreviation!)
# pkg   - package (discouraged abbreviation!)
# hfile - header file
# cfile - implementation file
# dep   - dependency (discouraged abbreviation!)


class XmlError(Exception):
    """Parsing errors in XML configuration file."""

    pass


class InvalidArgumentError(Exception):
    """General errors with invalid arguments."""

    pass


def warn(*args):
    """Logs a warning message."""
    logging.warn(*args)


def strip_ext(filename):
    """Strips the extension from a filename."""
    return os.path.splitext(filename)[0]


def path_normjoin(path, *paths):
    """Returns normalized result of joining of paths."""
    return os.path.normpath(os.path.join(path, *paths))


def path_common(paths):
    """Returns common prefix path for the argument absolute normalized paths."""
    path = os.path.commonprefix(paths)
    assert os.path.isabs(path)
    if path[-1] == os.path.sep:
        return path[:-1]
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


class Include(object):
    """Representation of an include directive.

    Attributes:
        with_quotes: True if the include is within quotes ("")
            instead of angle brackets (<>).
        hfile: The normalized path to the header file in the directive.
        hpath: The absolute path to the header file.
    """

    _RE_INCLUDE = re.compile(r'^\s*#include\s*'
                             '(<(?P<brackets>.+)>|"(?P<quotes>.+)")')

    __slots__ = ['__include_path', 'hfile', 'with_quotes', 'hpath']

    def __init__(self, include_path, with_quotes):
        """Initializes with attributes.

        Args:
            include_text: The original path in the include directive.
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

    @staticmethod
    def grep(file_path):
        """Processes include directives in a source file.

        Args:
            file_path: The full path to the source file.

        Yields:
            Include objects constructed with the directives.
        """
        with open(file_path) as src_file:
            for line in src_file:
                include = Include._RE_INCLUDE.search(line)
                if not include:
                    continue
                if include.group("brackets"):
                    yield Include(include.group("brackets"), with_quotes=False)
                else:
                    yield Include(include.group("quotes"), with_quotes=True)

    def locate(self, cwd, include_dirs):
        """Locates the included header file path.

        All input directory paths must be absolute.

        Args:
            cwd: The working directory for source file processing.
            include_dirs: The directories to search for the file,
                ordered from internal to external/system directories.

        Returns:
            The include directory if found;
            None, otherwise.
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
            return cwd
        iter_order = iter if self.with_quotes else reversed
        for include_dir in iter_order(include_dirs):
            if _find_in(include_dir):
                return include_dir
        return None


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
        self.name = strip_ext((cpath or hpath)[(len(package.root) + 1):])
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
        """Sanitizes and checkes includes."""
        def _check_duplicates(path, includes):
            unique_includes = set()
            for include in includes:
                if include in unique_includes:
                    warn('include issues: duplicate include:',
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
                    warn('include issues: redundant include:',
                         '%s in %s' % (str(include), self.cpath))
            self.includes_in_c.difference_update(self.includes_in_h)

        if self.hpath and self.cpath:
            hfile = os.path.basename(self.hpath)
            if hfile not in (os.path.basename(x.hfile)
                             for x in self.includes_in_c):
                warn('include issues: missing include:',
                     '%s does not include %s.' % (self.cpath, hfile))
            elif hfile != os.path.basename(self.includes_in_c[0].hfile):
                warn('include issues: include order:',
                     '%s should be the first include in %s.' %
                     (hfile, self.cpath))
        _remove_duplicates()
        _remove_redundant()


class ExternalComponent(object):
    """Representation of an external component.

    Note that external components are degenerate.
    There's no need to acquire full information about their dependencies.

    Attributes:
        hpath: Full path to the component header as an identifier.
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

    _RE_SRC = re.compile(r'(?i).*\.((?P<h>h(h|xx|\+\+|pp)?)|'
                         r'(?P<c>c(c|xx|\+\+|pp)?))$')

    def __init__(self, src_paths, include_paths, alias_paths, group, name=None):
        """Constructs an empty package.

        Registers the package in the package group.
        The argument paths are relative to the package group directory.

        Args:
            src_paths: The source directory paths (considered alias paths).
            include_paths: The export header paths (also alias paths).
            alias_paths: Additional directory paths aliasing to the package.
            group: The package group.
            name: A unique identifier within the package group.
                If not provided, only one path is accepted
                for the identifier deduction.

        Raises:
            InvalidArgumentError: Issues with the argument directory paths.
        """
        self.group = group
        self.src_paths = set()
        self.include_paths = set()
        self.alias_paths = set()
        self.__init_paths(src_paths, include_paths, alias_paths)
        assert self.alias_paths, 'No package directory paths are provided.'
        self.__init_name(name)
        self.root = path_common(self.alias_paths)
        self.components = []
        self.__dep_packages = None  # set of dependency packages
        group.add_package(self)

    def __str__(self):
        """For printing graph nodes."""
        return self.name

    def __init_paths(self, src_paths, include_paths, alias_paths):
        """Initializes package src, include, and alias paths."""
        def _update(path_container, arg_paths):
            for path in arg_paths:
                path = os.path.normpath(path)
                abs_path = path_normjoin(self.group.path, path)
                if not (os.path.isdir(abs_path) and
                        abs_path.startswith(self.group.path)):
                    raise InvalidArgumentError(
                        '%s is not a directory in %s (group %s).' %
                        (path, self.group.path, self.group.name))
                if abs_path in path_container:
                    # TODO: Report error with the package name.
                    raise InvalidArgumentError('%s is duplicated in %s' %
                                               (abs_path, self.group.name))
                path_container.add(abs_path)

        _update(self.src_paths, src_paths)
        _update(self.include_paths, include_paths)
        _update(self.alias_paths, alias_paths)
        self.alias_paths.update(self.src_paths, self.include_paths)

    def __init_name(self, name=None):
        """Initializes the package name."""
        assert name or len(self.alias_paths) == 1, 'Undefined package name.'
        if name:
            self.name = name
        else:
            for path in self.alias_paths:  # Single item in a generic container.
                path = os.path.relpath(path, self.group.path)
                self.name = '_'.join(x for x in path.split(os.path.sep) if x)

    def construct_components(self):
        """Traverses the package paths and constructs package components.

        Even though John Lakos defined a component as a pair of h and c files,
        C++ can have template only components
        residing only in header files (e.g., STL/Boost/etc.).
        Moreover, some header-only components
        may contain only inline functions or macros
        without any need for an implmentation file
        (e.g., inline math, Boost PPL).
        For these reasons, unpaired header files
        are counted as components by default.

        Unpaired c files are counted as incomplete components with warnings.
        """
        hpaths = []
        cpaths = []

        def _gather_files(path):
            for root, _, files in os.walk(path):
                for filename in files:
                    src_match = Package._RE_SRC.match(filename)
                    if src_match:
                        (hpaths if src_match.group('h')
                         else cpaths).append(os.path.join(root, filename))

        for src_path in self.src_paths:
            _gather_files(src_path)

        # This approach assumes
        # that the header and implementation are in the same directory.
        # TODO: Implement less-restricted, general pairing.
        cbases = dict((strip_ext(x), x) for x in cpaths)
        for hpath in hpaths:
            cpath = None
            key = strip_ext(hpath)
            if key in cbases:
                cpath = cbases[key]
                del cbases[key]
            self.components.append(Component(hpath, cpath, self))

        for cpath in cbases.values():
            self.components.append(Component(None, cpath, self))

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
        config_file: The path to the configuration file.
        external_components: {hpath: ExternalComponent}
        internal_components: {hpath: Component}
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
            XmlError: The XML is malformed or invalid.
            InvalidArgumentError: The configuration has is invalid values.
        """
        self.config_file = config_file
        self.external_components = {}
        self.internal_components = {}
        self.external_groups = {}
        self.internal_groups = {}
        self.include_dirs = []
        self.__package_aliases = []  # Sorted [(alias_path, external_package)]
        self.__parse_xml_config(config_file)
        self.__gather_include_dirs()
        self.__gather_aliases()

    def __parse_xml_config(self, config_file):
        """Parses the XML configuration file.

        Args:
            config_file: The path to the configuration file.

        Raises:
            XmlError: The XML is malformed or invalid.
            InvalidArgumentError: The configuration has is invalid values.
        """
        root = ElementTree.parse(config_file).getroot()
        for pkg_group_element in root.findall('package-group'):
            pkg_role = pkg_group_element.get('role')
            assert pkg_role is None or pkg_role in ('external', 'internal')
            pkg_groups = self.external_groups if pkg_role == 'external' \
                else self.internal_groups
            DependencyAnalysis.__add_package_group(pkg_group_element,
                                                   pkg_groups)

    @staticmethod
    def __add_package_group(pkg_group_element, pkg_groups):
        """Parses the body of <package-group/> in XML config file.

        Args:
            pkg_group_element: The <package-group> XML element.
            pkg_groups: The destination dictionary for member packages.

        Raises:
            InvalidArgumentError: Invalid configuration.
        """
        group_name = pkg_group_element.get('name')
        group_path = pkg_group_element.get('path')
        if group_name in pkg_groups:
            raise InvalidArgumentError('Redefinition of %s group' % group_name)

        package_group = PackageGroup(group_name, group_path)

        def _findall_text(element, query):
            return ('' if x.text is None else x.text.strip()
                    for x in element.findall(query))

        for pkg_element in pkg_group_element.findall('package'):
            Package(_findall_text(pkg_element, 'src-path'),
                    _findall_text(pkg_element, 'include-path'),
                    _findall_text(pkg_element, 'alias-path'),
                    package_group,
                    pkg_element.get('name'))
        # TODO: The following code is ugly. Find a better (Pythonic) way.
        for src_path in _findall_text(pkg_group_element, 'src-path'):
            Package((src_path,), (), (), package_group)
        for include_path in _findall_text(pkg_group_element, 'include-path'):
            Package((), (include_path,), (), package_group)
        for alias_path in _findall_text(pkg_group_element, 'alias-path'):
            Package((), (), (alias_path,), package_group)

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

    def locate(self, include, component):
        """Locates the dependency component.

        The current approach is naive.
        It searches for a file by its basename
        as if every subdirectory were an include path.

        Args:
            include: The include object representing the directive.
            component: The dependent component.

        Returns:
            True if the include is found.
        """
        include_dir = include.locate(component.working_dir, self.include_dirs)

        def _find_external_package():
            # TODO: Use include_dir as a hint if performance matters.
            # TODO: Use logN bisect with dir sort logic or graph.
            for path, package in reversed(self.__package_aliases):
                if path_isancestor(path, include.hpath):
                    return package
            assert False, 'Missing a directory from external groups.'

        if include_dir is None:
            return False
        if include.hpath in self.internal_components:
            dep_component = self.internal_components[include.hpath]
            if dep_component != component:
                component.dep_components.add(dep_component)
        else:
            if include.hpath in self.external_components:
                component.dep_components.add(
                    self.external_components[include.hpath])
            else:
                package = _find_external_package()
                dep_component = ExternalComponent(include.hpath, package)
                component.dep_components.add(dep_component)
                self.external_components[include.hpath] = dep_component
        return True

    def make_components(self):
        """Pairs hfiles and cfiles."""
        for group in self.internal_groups.values():
            for package in group.packages.values():
                package.construct_components()
                self.internal_components.update(
                    (x.hpath or x.cpath, x) for x in package.components)

    def analyze(self):
        """Runs the analysis."""
        for component in self.internal_components.values():
            for include in itertools.chain(component.includes_in_h,
                                           component.includes_in_c):
                if not self.locate(include, component):
                    warn('include issues: header not found: %s' % str(include))

    def make_graph(self, printer, args):
        """Reports analysis results and graphs."""
        def _analyze(suffix, digraph):
            digraph.analyze()
            digraph.print_cycles(printer)
            if not args.l and not args.L:
                digraph.print_levels(printer)
            else:
                digraph.print_levels(printer, args.l)
            digraph.print_summary(printer)
            digraph.write_dot(suffix)

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


def main():
    """Runs the dependency analysis and prints results and graphs.

    Raises:
        IOError: filesystem operations failed.
        XmlError: XML configuration validity issues.
        InvalidArgumentError: The configuration has is invalid values.
    """
    parser = ap.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='store_true', default=False,
                        help='show the version information and exit')
    parser.add_argument('-c', '--config', default='cppdep.xml',
                        help="""an XML file which describes
                        the source code structure of a C/C++ project""")
    parser.add_argument('-l', action='store_true', default=False,
                        help='list reduced dependencies of nodes')
    parser.add_argument('-L', action='store_true', default=False,
                        help='list unreduced dependencies of nodes')
    parser.add_argument('-o', '--output', metavar='path', help='output file')
    args = parser.parse_args()
    if args.version:
        print(VERSION)
        return
    analysis = DependencyAnalysis(args.config)
    analysis.make_components()
    analysis.analyze()
    printer = get_printer(args.output)
    analysis.make_graph(printer, args)


def get_printer(file_path=None):
    """Returns printer for the report."""
    destination = sys.stdout if not file_path else open(file_path, 'w')
    def _print(*args):
        print(*args, file=destination)
    return _print


if __name__ == '__main__':
    try:
        main()
    except IOError as err:
        logging.error('IO Error:\n' + str(err))
        sys.exit(1)
    except XmlError as err:
        logging.error('Configuration XML Error:\n' + str(err))
        sys.exit(1)
    except InvalidArgumentError as err:
        logging.error('Invalid Argument Error:\n' + str(err))
        sys.exit(1)
