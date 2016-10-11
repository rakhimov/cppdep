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


VERSION = '0.0.2'  # The latest release version.

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
_RE_SYSTEM_HFILE = re.compile(r'(?i)[^.]*$')
_RE_HFILE = re.compile(r'(?i).*\.h(xx|\+\+|h|pp|)$')
_RE_CFILE = re.compile(r'(?i).*\.c(xx|\+\+|c|pp|)$')


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
    """Returns a list of all header files from the given path.

    The directories are traversed recursively
    to extract header files from sub-directories.
    The effect is as-if the whole package header files were gathered.

    The function handles system headers specially
    by allowing extension-less header files.
    """
    return [hfile for hfile, _ in find(path, _RE_HFILE)] + \
           [hfile for hfile, _ in find(path, _RE_SYSTEM_HFILE)]


class Component(object):
    """Representation of a component in a package.

    Attributes:
        name: A unique name as an identifier of the component.
        hpath: The path to the header file of the component.
        cpath: The path to the implementation file of the component.
        package: (group_name, pkg_name)
        dep_internal_hfiles: Internal header files the component depends upon.
        dep_external_hfiles: External header files the component depends upon.
        dep_external_pkgs: External packages the component depends upon.
    """

    def __init__(self, name, hpath, cpath):
        """Initialization of a free-standing component.

        Args:
            name: A unique identifier name for the component.
            hpath: The path to the header file of the component.
            cpath: The path to the implementation file of the component.
        """
        self.name = name
        self.hpath = hpath
        self.cpath = cpath
        self.package = ('anonymous', 'anonymous')  # TODO: Reason for defaults?
        self.dep_internal_hfiles = set()
        self.dep_external_hfiles = set()
        self.dep_components = set()
        self.dep_external_pkgs = set()

    def __str__(self):
        return self.name


class IncompleteComponents(object):
    """A collection of unpaired header or source files."""

    def __init__(self):
        """Initializes an empty container."""
        self.__data = []  # [(group_name, pkg_name, hpaths, cpaths)]

    def register(self, group_name, pkg_name, hpaths, cpaths):
        """Registers unpaired files.

        Args:
            group_name: The name of the package group.
            pkg_name: The name of the package.
            hpaths: A collection of the header file path in the package.
            cpaths: A collection of the source file path in the package.

        Precondition:
            No duplicate packages.
        """
        if hpaths or cpaths:
            self.__data.append((group_name, pkg_name, hpaths, cpaths))

    def print_warning(self):
        """Prints a warning message about incomplete components."""
        if not self.__data:
            return
        message = ''
        for group_name, pkg_name, hpaths, cpaths in self.__data:
            message += 'in package %s.%s: ' % (group_name, pkg_name)
            message += ', '.join(os.path.basename(x) for x in hpaths)
            message += ' ' + ', '.join(os.path.basename(x) for x in cpaths)
            message += '\n'
        print('-' * 80)
        print('warning: detected files failed to associate '
              'with any component (all will be ignored): ')
        print(message)


class ComponentIncludeIssues(object):
    """Detector of include issues in a component."""

    def __init__(self):
        """Empty issues as success by default."""
        self.__non_first_hfile_include = []
        self.__indirect_hfile_include = []
        self.__missing_hfile_include = []

    def check(self, component, hfiles):
        """Checks for issues with header inclusion in implementation files.

        Args:
            component: The component under examination.
            hfiles: The header files included by the implementation file.
        """
        cpath = component.cpath
        hfile = os.path.basename(component.hpath)
        try:  # Check if the component header file is the first include.
            if hfiles.index(hfile):
                self.__non_first_hfile_include.append('%s: %s, should be %s.' %
                                                      (cpath, hfiles[0], hfile))
        except ValueError:  # The header include is missing.
            if hfile in component.dep_internal_hfiles:
                self.__indirect_hfile_include.append(
                    '%s: does not include %s directly.' % (cpath, hfile))
            else:
                self.__missing_hfile_include.append(
                    '%s: does not depend on %s.' % (cpath, hfile))

    def report(self):
        """Reports gathered issues with header inclusion."""
        def _print_all(messages):
            """Prints all error messages one on each line."""
            for message in messages:
                print(message)

        if self.__missing_hfile_include:
            print('-' * 80)
            print('warning: following every dotC does not depend on '
                  'its associated header: ')
            _print_all(self.__missing_hfile_include)

        if self.__indirect_hfile_include:
            print('-' * 80)
            print('warning: following every dotC does not include '
                  'its associated header directly: ')
            _print_all(self.__indirect_hfile_include)

        if self.__non_first_hfile_include:
            print('-' * 80)
            print('warning: following every dotC does not include '
                  'its associated header before other headers: ')
            _print_all(self.__non_first_hfile_include)


class Analysis(object):
    """Group of dependency analysis functions.

    Attributes:
        packages: {group_name: {pkg_name: [Component]}}
        components: {base_name: Component}
        external_hfiles: {hfile: (group_name, pkg_name)}
        internal_hfiles: {hfile: hpath}
    """

    def __init__(self):
        """Initializes analysis containers."""
        self.packages = {}
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
                    hfiles = find_external_hfiles(src_path)
                    for hfile in hfiles:
                        self.external_hfiles[hfile] = (group_name, pkg_name)

    def make_components(self, config):
        """Pairs hfiles and cfiles.

        Args:
            config: The project configurations with package groups.
        """
        self.__gather_external_hfiles(config.external_groups)

        incomplete_components = IncompleteComponents()
        for group_name, packages in config.internal_groups.items():
            self.packages[group_name] = {}
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

                hpaths, cpaths = \
                    self.construct_components(group_name, pkg_name, hbases, cbases)
                incomplete_components.register(group_name, pkg_name, hpaths, cpaths)

        # Report files failed to associated with any component
        incomplete_components.print_warning()

    def construct_components(self, group_name, pkg_name, hbases, cbases):
        """Pairs header and implementation files into components.

        Even though John Lakos defined a component as a pair of h and c files,
        C++ can have template only components
        residing only in header files (e.g., STL/Boost/etc.).
        Moreover, some header-only components
        may contain only inline functions or macros
        without any need for an implmentation file (e.g., inline math, Boost PPL).
        For these reason, unpaired header files
        are counted as components by default.

        Args:
            group_name: The name of the package group.
            pkg_name: The name of the package.
            hbases: Base names of header files.
            cbases: Base names of implementation files.

        Returns:
            collection(unpaired header paths), collection(unpaired source paths)

        TODO:
        Refactor Component to allow header-only/source-only components.

        TODO:
            Consider the main implementation file of an application
            as a separate component as well.

        TODO:
            Supply an option to disable unpaired header component considerations.
        """
        assert pkg_name not in self.packages[group_name]
        self.packages[group_name][pkg_name] = []
        # TODO: Workaround for Python 3.
        paired_components = set(hbases.keys()) & set(cbases.keys())
        for key in paired_components:
            assert key not in self.components
            component = Component(key, hbases[key], cbases[key])
            self.packages[group_name][pkg_name].append(component)
            component.package = (group_name, pkg_name)
            self.components[key] = component
            del hbases[key]  # TODO Smells?!
            del cbases[key]  # TODO Smells?!
        return hbases.values(), cbases.values()

    def __expand_hfile_deps(self, header_file):
        """Recursively expands include directives.

        Args:
            header_file: The source header file.

        Returns:
            (internal header files, external header files, unknown header files)
        """
        if header_file in self.__internal_hfile_deps:
            return self.__internal_hfile_deps[header_file]
        dep_internal_hfiles = set()
        dep_external_hfiles = set()
        dep_bad_hfiles = set()

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
                    # Detect headers failed to locate.
                    dep_bad_hfiles.add(hfile)
            next_hfiles.difference_update(dep_internal_hfiles)
            next_hfiles.difference_update(dep_external_hfiles)
            next_hfiles.difference_update(dep_bad_hfiles)
            current_hfiles = next_hfiles

        self.__internal_hfile_deps[header_file] = \
            (dep_internal_hfiles, dep_external_hfiles, dep_bad_hfiles)
        return dep_internal_hfiles, dep_external_hfiles, dep_bad_hfiles

    def make_cdep(self):
        """Determines all hfiles on which a cfile depends.

        Note:
            Simple recursive parsing does not work
            since there may be a cyclic dependency among headers.
        """
        missing_hfiles = set()
        include_issues = ComponentIncludeIssues()
        for component in self.components.values():
            hfiles = grep_hfiles(component.cpath)
            for hfile in hfiles:
                if hfile in self.external_hfiles:
                    component.dep_external_hfiles.add(hfile)
                    continue
                internal_hfiles, external_hfiles, unknown_hfiles = \
                    self.__expand_hfile_deps(hfile)
                component.dep_internal_hfiles.update(internal_hfiles)
                component.dep_external_hfiles.update(external_hfiles)
                missing_hfiles.update(unknown_hfiles)
            # Check for include issues only after gathering all includes.
            include_issues.check(component, hfiles)

        # Report headers failed to locate.
        if missing_hfiles:
            print('-' * 80)
            print('warning: failed to locate following headers: ')
            print(' '.join(missing_hfiles))
        include_issues.report()

    def show_hfile_deps(self, hfile, depth, dep_hfiles):
        if hfile in dep_hfiles:
            print('+' * depth + '%s (duplicated)' % hfile)
            return
        dep_hfiles.add(hfile)
        if hfile in self.internal_hfiles:
            hpath = self.internal_hfiles[hfile]
            hbase = filename_base(hfile)
            str_component = None
            if hbase in self.components:
                component = self.components[hbase]
                if os.path.basename(component.hpath) == hfile:
                    str_component = 'associates with %s in %s.%s' % (
                        component.name, component.package[0], component.package[1])
                else:
                    str_component = 'basename conflicts with %s in %s.%s' % (
                        component.name, component.package[0], component.package[1])
            else:
                str_component = 'does not associate with any component'
            print('+' * depth + '%s (%s, %s)' % (hfile, hpath, str_component))
            for dep_hfile in grep_hfiles(hpath):
                self.show_hfile_deps(dep_hfile, depth + 1, dep_hfiles)
        elif hfile in self.external_hfiles:
            print('+' * depth + '%s (in external package %s)' %
                  (hfile, '.'.join(self.external_hfiles[hfile])))
        else:
            print('+' * depth + '%s (failed to locate)' % hfile)

    def show_details_of_components(self):
        """Determines all hfiles on which the specific component depends.

        Very useful for trying to understand
        why a cross-component dependency occurs.
        """
        included_by = {}
        for component in self.components.values():
            depth = 1
            dep_hfiles = set()
            print('-' * 80)
            print('%s (%s in package %s.%s):' %
                  (component.name, component.cpath, component.package[0],
                   component.package[1]))
            for hfile in grep_hfiles(component.cpath):
                self.show_hfile_deps(hfile, depth, dep_hfiles)
            for hfile in dep_hfiles:
                if hfile in included_by:
                    included_by[hfile].append(component.cpath)
                else:
                    included_by[hfile] = [component.cpath]
        for hfile in sorted(list(included_by.keys())):
            print('-' * 80)
            print(hfile + ':')
            for cpath in sorted(included_by[hfile]):
                print(' ' + cpath)

    def make_ldep(self):
        """Determines all components on which a component depends."""
        for component in self.components.values():
            for hfile in component.dep_internal_hfiles:
                assert hfile in self.internal_hfiles
                hbase = filename_base(hfile)
                # An internal header that doesn't belong to any component
                # is warned by make_components().
                if hbase in self.components:
                    dep_component = self.components[hbase]
                    if dep_component != component:
                        assert os.path.basename(dep_component.hpath) == hfile
                        component.dep_components.add(dep_component)
            for hfile in component.dep_external_hfiles:
                assert hfile in self.external_hfiles
                component.dep_external_pkgs.add(self.external_hfiles[hfile])

    def output_ldep(self):
        for group_name in sorted(self.packages.keys()):
            for pkg_name in sorted(self.packages[group_name]):
                print('=' * 80)
                print('package %s.%s dependency:' % (group_name, pkg_name))
                for component in self.packages[group_name][pkg_name]:
                    message = '%s -> ' % component.name
                    message += ', '.join(sorted(x.name
                                                for x in component.dep_components))
                    message += '+(external packages) ' + ','.join(
                        sorted('.'.join(x) for x in component.dep_external_pkgs))
                    print(message)


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
            src_paths = [x.text.strip() for x in pkg_element.findall('path')]
            pkg_groups[group_name][pkg_name] = \
                [os.path.normpath(os.path.join(group_path, x))
                 for x in src_paths]

        for pkg_element in pkg_group_element.findall('path'):
            pkg_path = os.path.normpath(os.path.join(group_path,
                                                     pkg_element.text.strip()))
            pkg_name = os.path.basename(pkg_path)
            pkg_groups[group_name][pkg_name] = [pkg_path]

        for pkg_path in pkg_groups[group_name][pkg_name]:
            if not os.path.exists(pkg_path):
                raise ConfigXmlParseError("""detected a config error for package
                                             %s.%s: %s does not exist!""" %
                                          (group_name, pkg_name, pkg_path))


def make_graph(components, packages):
    print('@' * 80)
    print('analyzing dependencies among all components ...')
    digraph = graph.create_graph_all_component(components)
    graph.calculate_graph(digraph)

    print('@' * 80)
    print('analyzing dependencies among all packages ...')
    digraph, edge2deps, node2externalpkgs = \
        graph.create_graph_all_pkg(components)
    graph.output_original_graph_info(edge2deps, node2externalpkgs)
    graph.calculate_graph(digraph, 'all_packages')

    print('@' * 80)
    print('analyzing dependencies among all package groups ...')
    digraph, edge2deps, node2externalpkgs = \
        graph.create_graph_all_pkggrp(components)
    graph.output_original_graph_info(edge2deps, node2externalpkgs)
    graph.calculate_graph(digraph, 'all_pkggrps')

    for group_name in packages:
        print('@' * 80)
        print('analyzing dependencies among packages in ' +
              'the specified package group %s ...' % group_name)
        digraph, edge2deps, node2externalpkgs = \
            graph.create_graph_pkggrp_pkg(group_name, packages)
        graph.output_original_graph_info(edge2deps, node2externalpkgs)
        graph.calculate_graph(digraph, group_name)

    for group_name in packages:
        for pkg_name in packages[group_name]:
            print('@' * 80)
            print('analyzing dependencies among components in ' +
                  'the specified pakcage %s.%s ...' % (group_name, pkg_name))
            digraph = \
                graph.create_graph_pkg_component(group_name, pkg_name, packages)
            graph.calculate_graph(digraph, group_name + '.' + pkg_name)


def main():
    parser = ap.ArgumentParser(description=__doc__)

    parser.add_argument('--version', action='store_true', default=False,
                        help='show the version information and exit')

    parser.add_argument('-f', '--conf', dest='path_conf', default='cppdep.xml',
                        help="""an XML file which describes
                        the source code structure of a C/C++ project""")

    parser.add_argument('-d', '--debug', dest='details_of_components',
                        action='store_true', default=False,
                        help="""show all warnings and details
                        of every component (aka. includes/included by),
                        but not analyze dependencies.""")

    args = parser.parse_args()

    if args.version:
        print(VERSION)
        return 0

    config = Config(args.path_conf)
    analysis = Analysis()
    analysis.make_components(config)
    analysis.make_cdep()

    if args.details_of_components:
        analysis.show_details_of_components()
        return 0

    analysis.make_ldep()
    analysis.output_ldep()
    make_graph(analysis.components, analysis.packages)


if __name__ == '__main__':
    try:
        main()
    except IOError as err:
        print("IO Error:\n" + str(err))
        sys.exit(1)
    except ConfigXmlParseError as err:
        print("Configuration XML Error:\n" + str(err))
        sys.exit(1)
