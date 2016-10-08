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


class ConfigXmlParseError(Exception):
    """Parsing errors in XML configuration file."""

    pass


def filename_base(filename):
    """Strips the extension from a filename."""
    return os.path.splitext(filename)[0]


# A search pattern for include directives.
_RE_INCLUDE = re.compile(r'^\s*#include\s*(<(?P<system>.+)>|"(?P<local>.+)")')


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


# STL/Boost/Qt and other libraries can provide extension-less system headers.
_RE_SYSTEM_HFILE = re.compile(r'(?i)[^.]*$')
_RE_HFILE = re.compile(r'(?i).*\.h(xx|\+\+|h|pp|)$')
_RE_CFILE = re.compile(r'(?i).*\.c(xx|\+\+|c|pp|)$')


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


class Component(object):

    def __init__(self, name, hpath, cpath):
        self.package = ('anonymous', 'anonymous')
        self.name = name
        self.hpath = hpath
        self.cpath = cpath
        self.dep_internal_hfiles = set()
        self.dep_external_hfiles = set()
        self.dep_components = set()
        self.dep_external_pkgs = set()

    def __str__(self):
        return self.name


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
            self.__add_package_group(pkg_group_element, pkg_groups)

    def __add_package_group(self, pkg_group_element, pkg_groups):
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


external_hfiles = {}  # {hfile: (group_name, pkg_name)}
internal_hfiles = {}  # {hfile: hpath}

pkgs = {}  # {group_name: {pkg_name: [Component]}}
components = {}  # {base_name: Component}


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


def gather_external_hfiles(external_groups):
    """Populates databases of external dependency headers.

    Args:
        external_groups: A database of external groups and its source paths.

    Returns:
        {hfile: (group_name, pkg_name)}
    """
    external_hfiles = {}
    for group_name, packages in external_groups.items():
        for pkg_name, src_paths in packages.items():
            for src_path in src_paths:
                hfiles = find_external_hfiles(src_path)
                for hfile in hfiles:
                    external_hfiles[hfile] = (group_name, pkg_name)
    return external_hfiles


class IncompleteComponents(object):
    """A collection of unpaired header or source files. """

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


def make_components(config):
    """Pairs hfiles and cfiles.

    Args:
        config: The project configurations with package groups.
    """
    global external_hfiles
    external_hfiles = gather_external_hfiles(config.external_groups)

    incomplete_components = IncompleteComponents()
    for group_name, packages in config.internal_groups.items():
        pkgs[group_name] = {}
        for pkg_name, src_paths in packages.items():
            hbases = {}
            cbases = {}
            hfiles = {}
            for src_path in src_paths:
                find_hfiles(src_path, hbases, hfiles)
                find_cfiles(src_path, cbases)

            for hfile, hpath in hfiles.items():
                if hfile not in internal_hfiles:
                    internal_hfiles[hfile] = hpath

            hpaths, cpaths = \
                construct_components(group_name, pkg_name, hbases, cbases)
            incomplete_components.register(group_name, pkg_name, hpaths, cpaths)

    # Report files failed to associated with any component
    incomplete_components.print_warning()


def construct_components(group_name, pkg_name, hbases, cbases):
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
    assert pkg_name not in pkgs[group_name]
    pkgs[group_name][pkg_name] = []
    paired_components = hbases.viewkeys() & cbases.viewkeys()
    for key in paired_components:
        # Detect cross-package conflicts among internal dotCs
        # In fact, only check between registering components
        # and registered components.
        # For example, suppose both libA/main.cc and libB/main.cpp
        # failed to be registered as a component,
        # the basename conflict between them will be ignored.
        assert key not in components
        component = Component(key, hbases[key], cbases[key])
        pkgs[group_name][pkg_name].append(component)
        component.package = (group_name, pkg_name)
        components[key] = component
        del hbases[key]  # TODO Smells?!
        del cbases[key]  # TODO Smells?!
    return hbases.values(), cbases.values()


def expand_hfile_deps(header_file):
    """Recursively expands include directives.

    Args:
        header_file: The source header file.

    Returns:
        (internal header files, external header files, unknown header files)
    """
    dep_internal_hfiles = set()
    dep_external_hfiles = set()
    dep_bad_hfiles = set()

    current_hfiles = set([header_file])
    while current_hfiles:
        next_hfiles = set()
        for hfile in current_hfiles:
            if hfile in internal_hfiles:
                dep_internal_hfiles.add(hfile)
                hpath = internal_hfiles[hfile]
                next_hfiles.update(grep_hfiles(hpath))
            elif hfile in external_hfiles:
                dep_external_hfiles.add(hfile)
            else:
                # Detect headers failed to locate.
                dep_bad_hfiles.add(hfile)
        next_hfiles.difference_update(dep_internal_hfiles)
        next_hfiles.difference_update(dep_external_hfiles)
        next_hfiles.difference_update(dep_bad_hfiles)
        current_hfiles = next_hfiles

    return (dep_internal_hfiles, dep_external_hfiles, dep_bad_hfiles)


def make_cdep():
    """Determines all hfiles on which a cfile depends.

    Note:
        Simple recursive parsing does not work
        since there may be a cyclic dependency among headers.
    """
    bad_hfiles = set()
    hfile_deps = {}
    message = ''
    message2 = ''
    message3 = ''
    for component in components.values():
        cpath = component.cpath
        hfiles = grep_hfiles(cpath)
        if not hfiles:
            continue
        comp_hfile = os.path.basename(component.hpath)
        # Detect first header issues issues.
        ind_comp_hfile = -1
        try:
            ind_comp_hfile = hfiles.index(comp_hfile)
            if ind_comp_hfile != 0:
                message += '%s: %s, should be %s.\n' % (
                    cpath, hfiles[0], comp_hfile)
        except ValueError:
            pass
        for hfile in hfiles:
            if hfile in external_hfiles:
                component.dep_external_hfiles.add(hfile)
                continue
            if hfile in hfile_deps:
                (set1, set2, set3) = hfile_deps[hfile]
            else:
                (set1, set2, set3) = expand_hfile_deps(hfile)
                hfile_deps[hfile] = (set1, set2, set3)
            component.dep_internal_hfiles.update(set1)
            component.dep_external_hfiles.update(set2)
            bad_hfiles.update(set3)
        # Detect indirectly including issues, and non-dependent issues.
        if ind_comp_hfile < 0:
            if comp_hfile in component.dep_internal_hfiles:
                message2 += '%s: does not include %s directly.\n' % (
                    cpath, comp_hfile)
            else:
                message3 += '%s: does not depend on %s.\n' % (
                    cpath, comp_hfile)
    # Report headers failed to locate.
    if bad_hfiles:
        print('-' * 80)
        print('warning: failed to locate following headers: ')
        print(' '.join(bad_hfiles))
    # Report non-dependent issues.
    if message3:
        print('-' * 80)
        print('warning: following every dotC does not depend on ' +
              'its associated header: ')
        print(message3)
    # Report indirectly including issues.
    if message2:
        print('-' * 80)
        print('warning: following every dotC does not include ' +
              'its associated header directly: ')
        print(message2)
    # Report first header issues.
    if message:
        print('-' * 80)
        print('warning: following every dotC does not include ' +
              'its associated header before other headers: ')
        print(message)


def show_hfile_deps(hfile, depth, dep_hfiles):
    if hfile in dep_hfiles:
        print('+' * depth + '%s (duplicated)' % hfile)
        return
    dep_hfiles.add(hfile)
    if hfile in internal_hfiles:
        hpath = internal_hfiles[hfile]
        hbase = filename_base(hfile)
        str_component = None
        if hbase in components:
            component = components[hbase]
            if os.path.basename(component.hpath) == hfile:
                str_component = 'associates with %s in %s.%s' % (
                    component.name, component.package[0], component.package[1])
            else:
                str_component = 'basename conflicts with %s in %s.%s' % (
                    component.name, component.package[0], component.package[1])
        else:
            str_component = 'does not associate with any component'
        print('+' * depth + '%s (%s, %s)' % (hfile, hpath, str_component))
        for hfile2 in grep_hfiles(hpath):
            show_hfile_deps(hfile2, depth + 1, dep_hfiles)
    elif hfile in external_hfiles:
        print('+' * depth + '%s (in external package %s)' %
              (hfile, '.'.join(external_hfiles[hfile])))
    else:
        print('+' * depth + '%s (failed to locate)' % hfile)


def show_details_of_components():
    """Determines all hfiles on which the specific component depends.

    Very useful for trying to understand
    why a cross-component dependency occurs.
    """
    included_by = {}
    for component in components.values():
        depth = 1
        dep_hfiles = set()
        print('-' * 80)
        print('%s (%s in package %s.%s):' %
              (component.name, component.cpath, component.package[0],
               component.package[1]))
        for hfile in grep_hfiles(component.cpath):
            show_hfile_deps(hfile, depth, dep_hfiles)
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


def make_ldep():
    """Determines all components on which a component depends."""
    for component in components.values():
        for hfile in component.dep_internal_hfiles:
            assert hfile in internal_hfiles
            hbase = filename_base(hfile)
            if hbase in components:
                comp2 = components[hbase]
                # We've reported hfile basename conflicts at make_components().
                if comp2 != component and os.path.basename(comp2.hpath) == hfile:
                    component.dep_components.add(comp2)
            else:
                # This internal header doesn't belong to any component.
                # We've ever warned it at make_components().
                pass
        for hfile in component.dep_external_hfiles:
            assert hfile in external_hfiles
            external_pkg = external_hfiles[hfile]
            component.dep_external_pkgs.add(external_pkg)


def output_ldep():
    for group_name in sorted(pkgs.keys()):
        for pkg_name in sorted(pkgs[group_name]):
            print('=' * 80)
            print('pakcage %s.%s dependency:' % (group_name, pkg_name))
            for component in pkgs[group_name][pkg_name]:
                message = '%s -> ' % component.name
                message += ', '.join(sorted(x.name
                                            for x in component.dep_components))
                message += '+(external packages) ' + ','.join(
                    sorted('.'.join(x) for x in component.dep_external_pkgs))
                print(message)


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
    make_components(config)

    make_cdep()

    if args.details_of_components:
        show_details_of_components()
        return 0

    make_ldep()

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

    for group_name in pkgs:
        print('@' * 80)
        print('analyzing dependencies among packages in ' +
              'the specified package group %s ...' % group_name)
        digraph, edge2deps, node2externalpkgs = \
            graph.create_graph_pkggrp_pkg(group_name, pkgs)
        graph.output_original_graph_info(edge2deps, node2externalpkgs)
        graph.calculate_graph(digraph, group_name)

    for group_name in pkgs:
        for pkg_name in pkgs[group_name]:
            print('@' * 80)
            print('analyzing dependencies among components in ' +
                  'the specified pakcage %s.%s ...' % (group_name, pkg_name))
            digraph = \
                graph.create_graph_pkg_component(group_name, pkg_name, pkgs)
            graph.calculate_graph(digraph, group_name + '.' + pkg_name)


if __name__ == '__main__':
    try:
        main()
    except IOError as err:
        print("IO Error:\n" + str(err))
        sys.exit(1)
    except ConfigXmlParseError as err:
        print("Configuration XML Error:\n" + str(err))
        sys.exit(1)
