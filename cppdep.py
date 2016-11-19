#!/usr/bin/env python
#
# Copyright (C) 2016 Olzhas Rakhimov
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
import os.path
import re
import sys
from xml.etree import ElementTree

import graph


VERSION = '0.0.6'  # The latest release version.

# Allowed common abbreviations in the code:
# ccd   - Cumulative Component Dependency (CCD)
# nccd  - Normalized CCD
# accd  - Average CCD
# cd    - component dependency (discouraged abbreviation!)
# pkg   - package (discouraged abbreviation!)
# hfile - header file
# cfile - implementation file
# dep   - dependency (discouraged abbreviation!)


# A search pattern for include directives.
_RE_INCLUDE = re.compile(r'^\s*#include\s*(<(?P<system>.+)>|"(?P<local>.+)")')
# STL/Boost/Qt and other libraries can provide extension-less system headers.
_RE_SYSTEM_HFILE = re.compile(r'[^.]*$')
_RE_HFILE = re.compile(r'(?i).*\.h(xx|\+\+|h|pp|)$')
_RE_CFILE = re.compile(r'(?i).*\.c(xx|\+\+|c|pp|)$')


def warn(*args, **kwargs):
    """Prints a warning message into the standard error."""
    print(*args, file=sys.stderr, **kwargs)


def filename_base(filename):
    """Strips the extension from a filename."""
    return os.path.splitext(filename)[0]


def grep_include(file_obj):
    """Finds include directives in source files.

    Args:
        file_obj: A source file opened for read.

    Yields:
        The string name of included header file.
    """
    for line in file_obj:
        match_text = _RE_INCLUDE.search(line)
        if match_text:
            yield match_text.group("system") or match_text.group("local")


def grep_hfiles(src_file_path):
    """Processes include directives in source files.

    Args:
        src_file_path: The path to the source file to parse.

    Returns:
        A list of inlcuded header files into the argument source file.
    """
    with open(src_file_path) as src_file:
        return [os.path.basename(header) for header in grep_include(src_file)]


def find(path, fnmatcher):
    """Yields basename and full path to header files.

    Args:
        path: The root path to start the search.
        fnmatcher: regex for filename.
    """
    if os.path.isfile(path):
        filename = os.path.basename(path)
        if fnmatcher.match(filename):
            yield filename, path
    else:
        for root, _, files in os.walk(path):
            for entry in files:
                if fnmatcher.match(entry):
                    full_path = os.path.join(root, entry)
                    yield entry, full_path


def find_hfiles(path, hbases, hfiles):
    """Finds package header files.

    Args:
        path: The root path to start the search.
        hbases: The destination container for header file basenames.
        hfiles: The destination container for header file paths.
    """
    for hfile, hpath in find(path, _RE_HFILE):
        if hfile not in hfiles:
            hfiles[hfile] = hpath
        hbase = filename_base(hfile)
        hbases[hbase] = hpath


def find_cfiles(path, cbases):
    """Finds package implement files.

    Args:
        path: The root path to start the search.
        cbases: The destination container for implementation file basenames.
    """
    for cfile, cpath in find(path, _RE_CFILE):
        cbase = filename_base(cfile)
        assert cbase not in cbases
        cbases[cbase] = cpath


def find_external_hfiles(path):
    """Yields header files from the given path.

    The directories are traversed recursively
    to extract header files from sub-directories.
    The effect is as-if the whole package header files were gathered.

    The function handles system headers specially
    by allowing extension-less header files.
    """
    for hfile, _ in find(path, _RE_HFILE):
        yield hfile
    for hfile, _ in find(path, _RE_SYSTEM_HFILE):
        yield hfile


class Component(object):
    """Representation of a component in a package.

    Attributes:
        name: A unique name as an identifier of the component.
        hpath: The path to the header file of the component.
        cpath: The path to the implementation file of the component.
        package: The package this components belongs to.
        dep_internal_hfiles: Internal header files the component depends upon.
        dep_external_hfiles: External header files the component depends upon.
        dep_external_pkgs: External packages the component depends upon.
    """

    def __init__(self, name, hpath, cpath, package):
        """Initialization of a free-standing component.

        Registers the component in the package upon initialization.
        Warns about incomplete components.

        Args:
            name: A unique identifier name for the component.
            hpath: The path to the header file of the component.
            cpath: The path to the implementation file of the component.
            package: The package this components belongs to.
        """
        assert hpath or cpath
        if not hpath:
            warn('warning: incomplete component: missing header: %s in %s.%s' %
                 (name, package.name, package.group.name))
        self.name = name
        self.hpath = hpath
        self.cpath = cpath
        self.package = package
        self.dep_internal_hfiles = set()
        self.dep_external_hfiles = set()
        self.dep_components = set()
        self.dep_external_pkgs = set()
        package.components.append(self)

    def __str__(self):
        """For printing graph nodes."""
        return self.name

    def dependencies(self):
        """Yeilds dependency components within the same package."""
        for dep_component in self.dep_components:
            if dep_component.package == self.package:
                yield dep_component


class Package(object):
    """A collection of components.

    Attributes:
        name: The unique identifier name of the package.
        components: The list of unique components in this package.
        group: The package group this package belongs to.
    """

    def __init__(self, name, group):
        """Constructs an empty package.

        Registers the package in the package group.

        Args:
            name: A unique identifier string.
            group: The package group.
        """
        self.name = name
        self.components = []
        self.group = group
        group.packages[name] = self

    def __str__(self):
        """For printing graph nodes."""
        return self.name

    def dependencies(self):
        """Yields dependency packages within the same package group."""
        for component in self.components:
            for dep_component in component.dep_components:
                if (dep_component.package.group == self.group and
                        dep_component.package != self):
                    yield dep_component.package


class PackageGroup(object):
    """A collection of packages.

    Attributes:
        name: The unique name of the package group.
        packages: {package_name: package} belonging to this group.
    """

    def __init__(self, name):
        """Constructs an empty group.

        Atgs:
            name: A unique identifier string.
        """
        self.name = name
        self.packages = {}

    def __str__(self):
        """For printing graph nodes."""
        return self.name

    def dependencies(self):
        """Yields dependency package groups."""
        for package in self.packages.values():
            for component in package.components:
                for dep_component in component.dep_components:
                    if dep_component.package.group != self:
                        yield dep_component.package.group


class ComponentIncludeIssues(object):
    """Detector of include issues in a component."""

    @staticmethod
    def check(component, hfiles):
        """Checks for issues with header inclusion in implementation files.

        Args:
            component: The component under examination.
            hfiles: The header files included by the implementation file.
        """
        if not component.hpath or not component.cpath:
            return  # Header-only or incomplete components.
        cpath = component.cpath
        hfile = os.path.basename(component.hpath)
        try:  # Check if the component header file is the first include.
            if hfiles.index(hfile):
                warn('warning: include issues: include order: '
                     '%s: %s should be the first include.' % (cpath, hfile))
        except ValueError:  # The header include is missing.
            if hfile in component.dep_internal_hfiles:
                warn('warning: include issues: indirect include: '
                     '%s: does not include %s directly.' % (cpath, hfile))
            else:
                warn('warning: include issues: missing include: '
                     '%s: does not depend on %s.' % (cpath, hfile))


class DependencyAnalysis(object):
    """Analysis of dependencies with package groups/packages/components.

    Attributes:
        package_groups: {group_name: PackageGroup}
        components: {base_name: Component}
        external_hfiles: {hfile: (group_name, pkg_name)}
        internal_hfiles: {hfile: hpath}
    """

    def __init__(self):
        """Initializes analysis containers."""
        self.package_groups = {}
        self.components = {}
        self.external_hfiles = {}
        self.internal_hfiles = {}
        self.__internal_hfile_deps = {}

    def __gather_external_hfiles(self, external_groups):
        """Populates databases of external dependency headers.

        Args:
            external_groups: A database of external groups and its source paths.
        """
        for group_name, packages in external_groups.items():
            for pkg_name, src_paths in packages.items():
                for src_path in src_paths:
                    for hfile in find_external_hfiles(src_path):
                        self.external_hfiles[hfile] = (group_name, pkg_name)

    def make_components(self, config):
        """Pairs hfiles and cfiles.

        Args:
            config: The project configurations with package groups.
        """
        self.__gather_external_hfiles(config.external_groups)

        for group_name, packages in config.internal_groups.items():
            assert group_name not in self.package_groups
            package_group = PackageGroup(group_name)
            for pkg_name, src_paths in packages.items():
                hbases = {}
                cbases = {}
                hfiles = {}
                for src_path in src_paths:
                    find_hfiles(src_path, hbases, hfiles)
                    find_cfiles(src_path, cbases)

                for hfile, hpath in hfiles.items():
                    if hfile not in self.internal_hfiles:
                        self.internal_hfiles[hfile] = hpath

                self.__construct_components(pkg_name, package_group, hbases,
                                            cbases)
            self.package_groups[group_name] = package_group

    def __construct_components(self, pkg_name, group, hbases, cbases):
        """Pairs header and implementation files into components.

        Even though John Lakos defined a component as a pair of h and c files,
        C++ can have template only components
        residing only in header files (e.g., STL/Boost/etc.).
        Moreover, some header-only components
        may contain only inline functions or macros
        without any need for an implmentation file
        (e.g., inline math, Boost PPL).
        For these reasons, unpaired header files
        are counted as components by default.

        Args:
            pkg_name: The name of the package.
            group: The package group.
            hbases: Base names of header files.
            cbases: Base names of implementation files.
                    The paired base names will be removed from this container.

        Returns:
            Package containing the components
        """
        package = Package(pkg_name, group)

        for key, hpath in hbases.items():
            cpath = None
            if key in cbases:
                cpath = cbases[key]
                del cbases[key]
            assert key not in self.components
            self.components[key] = Component(key, hpath, cpath, package)

        for key, cpath in cbases.items():
            assert key not in self.components
            self.components[key] = Component(key, None, cpath, package)

        return package

    def __expand_hfile_deps(self, header_file):
        """Recursively expands include directives.

        Produces warning if a header file is not found.

        Args:
            header_file: The source header file.

        Returns:
            (internal header files, external header files)
        """
        if header_file not in self.__internal_hfile_deps:
            dep_internal_hfiles = set()
            dep_external_hfiles = set()
            dep_missing_hfiles = set()
            current_hfiles = set([header_file])
            while current_hfiles:
                next_hfiles = set()
                for hfile in current_hfiles:
                    if hfile in self.internal_hfiles:
                        dep_internal_hfiles.add(hfile)
                        hpath = self.internal_hfiles[hfile]
                        next_hfiles.update(grep_hfiles(hpath))
                    elif hfile in self.external_hfiles:
                        dep_external_hfiles.add(hfile)
                    else:
                        warn('warning: include issues: header not found: %s' %
                             hfile)
                        dep_missing_hfiles.add(hfile)
                next_hfiles.difference_update(dep_internal_hfiles)
                next_hfiles.difference_update(dep_external_hfiles)
                next_hfiles.difference_update(dep_missing_hfiles)
                current_hfiles = next_hfiles

            self.__internal_hfile_deps[header_file] = \
                (dep_internal_hfiles, dep_external_hfiles)
        return self.__internal_hfile_deps[header_file]

    def make_cdep(self):
        """Determines all hfiles on which a cfile depends.

        Note:
            Simple recursive parsing does not work
            since there may be a cyclic dependency among headers.
        """
        for component in self.components.values():
            hfiles = grep_hfiles(component.cpath or component.hpath)
            for hfile in hfiles:
                internal_hfiles, external_hfiles = \
                    self.__expand_hfile_deps(hfile)
                component.dep_internal_hfiles.update(internal_hfiles)
                component.dep_external_hfiles.update(external_hfiles)
            # Check for include issues only after gathering all includes.
            ComponentIncludeIssues.check(component, hfiles)

    def make_ldep(self):
        """Determines all components on which a component depends."""
        for component in self.components.values():
            for hfile in component.dep_internal_hfiles:
                assert hfile in self.internal_hfiles
                hbase = filename_base(hfile)
                if hbase in self.components:
                    dep_component = self.components[hbase]
                    if dep_component != component:
                        assert os.path.basename(dep_component.hpath) == hfile
                        component.dep_components.add(dep_component)
            for hfile in component.dep_external_hfiles:
                assert hfile in self.external_hfiles
                component.dep_external_pkgs.add(self.external_hfiles[hfile])

    def print_ldep(self):
        """Prints link time dependencies of components."""
        def _print_deps(deps):
            for name in sorted(deps):
                print('\t%s' % name)

        for group_name in sorted(self.package_groups.keys()):
            packages = self.package_groups[group_name].packages
            for pkg_name in sorted(packages.keys()):
                print('=' * 80)
                print('package %s.%s dependency:' % (group_name, pkg_name))
                for component in packages[pkg_name].components:
                    print('%s:' % component.name)
                    _print_deps(x.name for x in component.dep_components)
                    print('  (external)')
                    _print_deps('.'.join(x) for x in
                                component.dep_external_pkgs)

    def make_graph(self):
        """Reports analysis results and graphs."""
        def _analyze(suffix, arg_components):
            digraph = graph.Graph(arg_components)
            digraph.analyze()
            digraph.print_cycles()
            digraph.print_levels()
            digraph.print_summary()
            digraph.write_dot(suffix)

        if len(self.package_groups) > 1:
            print('\n' + '#' * 80)
            print('analyzing dependencies among all package groups ...')
            _analyze('system', self.package_groups.values())

        for group_name, package_group in self.package_groups.items():
            if len(package_group.packages) > 1:
                print('\n' + '#' * 80)
                print('analyzing dependencies among packages in ' +
                      'the specified package group %s ...' % group_name)
                _analyze(group_name, package_group.packages.values())

        for group_name, package_group in self.package_groups.items():
            for pkg_name, package in package_group.packages.items():
                print('\n' + '#' * 80)
                print('analyzing dependencies among components in ' +
                      'the specified package %s.%s ...' %
                      (group_name, pkg_name))
                _analyze('_'.join((group_name, pkg_name)), package.components)


class ConfigXmlParseError(Exception):
    """Parsing errors in XML configuration file."""

    pass


class Config(object):
    """Project configurations.

    Attributes:
        external_groups: External dependency packages and package groups.
                         {pkg_group_name: {pkg_name: [full_src_paths]}}
        internal_groups: The package groups of the project under analysis.
                         {pkg_group_name: {pkg_name: [full_src_paths]}}
    """

    def __init__(self, config_file):
        """Initializes configuraions from an XML config file.

        Args:
            config_file: The path to the XML config file.

        Raises:
            ConfigXmlParseError: The configuration or XML is invalid.
        """
        self.external_groups = {}
        self.internal_groups = {}
        self.__parse_xml_config(config_file)

    def __parse_xml_config(self, config_file):
        """Parses the XML configuration file.

        Args:
            config_file: The path to the configuration file.

        Raises:
            ConfigXmlParseError: The configuration or XML is invalid.
        """
        root = ElementTree.parse(config_file).getroot()
        for pkg_group_element in root.findall('package-group'):
            pkg_role = pkg_group_element.get('role')
            assert pkg_role is None or pkg_role in ('external', 'internal')
            pkg_groups = self.external_groups if pkg_role == 'external' \
                else self.internal_groups
            Config.__add_package_group(pkg_group_element, pkg_groups)

    @staticmethod
    def __add_package_group(pkg_group_element, pkg_groups):
        """Parses the body of <package-group/> in XML config file.

        Args:
            pkg_group_element: The <package-group> XML element.
            pkg_groups: The destination dictionary for member packages.

        Raises:
            ConfigXmlParseError: Invalid configuration or parsing error.
        """
        group_name = pkg_group_element.get('name')
        group_path = pkg_group_element.get('path')
        assert group_name not in pkg_groups  # TODO: Handle duplicate groups.
        pkg_groups[group_name] = {}

        for pkg_element in pkg_group_element.findall('package'):
            pkg_name = pkg_element.get('name')
            pkg_groups[group_name][pkg_name] = \
                [os.path.normpath(os.path.join(group_path, x.text.strip()))
                 for x in pkg_element.findall('path')]

        for pkg_element in pkg_group_element.findall('path'):
            pkg_path = os.path.normpath(os.path.join(group_path,
                                                     pkg_element.text.strip()))
            pkg_name = os.path.basename(pkg_path)
            pkg_groups[group_name][pkg_name] = [pkg_path]

        for pkg_name, pkg_paths in pkg_groups[group_name].items():
            for pkg_path in pkg_paths:
                if not os.path.exists(pkg_path):
                    raise ConfigXmlParseError(
                        "package %s.%s: %s does not exist!" %
                        (group_name, pkg_name, pkg_path))


def main():
    """Runs the dependency analysis and prints results and graphs.

    Raises:
        IOError: filesystem operations failed.
        ConfigXmlParseError: XML configuration validity issues.
    """
    parser = ap.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='store_true', default=False,
                        help='show the version information and exit')

    parser.add_argument('-c', '--config', default='cppdep.xml',
                        help="""an XML file which describes
                        the source code structure of a C/C++ project""")
    args = parser.parse_args()
    if args.version:
        print(VERSION)
        return
    config = Config(args.config)
    analysis = DependencyAnalysis()
    analysis.make_components(config)
    analysis.make_cdep()
    analysis.make_ldep()
    analysis.print_ldep()
    analysis.make_graph()


if __name__ == '__main__':
    try:
        main()
    except IOError as err:
        warn("IO Error:\n" + str(err))
        sys.exit(1)
    except ConfigXmlParseError as err:
        warn("Configuration XML Error:\n" + str(err))
        sys.exit(1)
