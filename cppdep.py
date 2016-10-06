#!/usr/bin/env python
#
# Copyright (C) 2016 cppdep developers
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

import sys
import os.path
import re
import hashlib
import math
import time
# ElementTree is introduced in by Python 2.5.
from xml.etree import ElementTree
import argparse as ap

import networkx as nx
from networkx.drawing.nx_pydot import write_dot
from networkx_ext import calc_ccd, make_dag, layering_dag

class ConfigXmlParseError(Exception):
    """Parsing errors in XML configuration file."""

    pass


def md5sum(fpath):
    """Converts a byte string into hashed hex representation.

    Args:
        fpath: A path to a file with the content to be hashed.
    """
    with open(fpath, 'rb') as input_file:
        return hashlib.md5(input_file.read()).hexdigest()


def fn_base(fn):
    return os.path.splitext(fn)[0]


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
    """Yields basename and full path to header files."""
    if os.path.isfile(path):
        fn = os.path.basename(path)
        if fnmatcher.match(fn):
            yield fn, path
    else:
        for root, dirs, files in os.walk(path):
            for entry in files:
                if fnmatcher.match(entry):
                    full_path = os.path.join(root, entry)
                    yield entry, full_path


def find_hfiles_blindly(path):
    return [hfile for hfile, _ in find(path, _RE_HFILE)] + \
           [hfile for hfile, _ in find(path, _RE_SYSTEM_HFILE)]


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
        pkg_groups[group_name] = {}  # TODO: Handle duplicate groups.

        for pkg_element in pkg_group_element.findall('package'):
            pkg_name = pkg_element.get('name')
            src_paths = pkg_element.text.strip().split()
            pkg_groups[group_name][pkg_name] = \
                [os.path.normpath(os.path.join(group_path, x))
                 for x in src_paths]

        for pkg_path in pkg_group_element.text.strip().split():
            pkg_path = os.path.normpath(os.path.join(group_path, pkg_path))
            pkg_name = os.path.basename(pkg_path)
            pkg_groups[group_name][pkg_name] = [pkg_path]

        for pkg_path in pkg_groups[group_name][pkg_name]:
            if not os.path.exists(pkg_path):
                raise ConfigXmlParseError("""detected a config error for package
                                             %s.%s: %s does not exist!""" %
                                          (group_name, pkg_name, pkg_path))


dict_external_hfiles = {}
dict_internal_hfiles = {}

dict_internal_conflict_hbases = {}
dict_internal_conflict_cbases = {}

dict_pkgs = {}
components = {}


def find_hfiles(path, hbases, hfiles):
    global dict_internal_conflict_hbases  # TODO: Smells?!
    for hfile, hpath in find(path, _RE_HFILE):
        if hfile not in hfiles:
            hfiles[hfile] = hpath
        hbase = fn_base(hfile)
        # Detect conflicts among internal headers inside a package
        if hbase in hbases:
            if hbase not in dict_internal_conflict_hbases:
                dict_internal_conflict_hbases[hbase] = [hbases[hbase]]
            dict_internal_conflict_hbases[hbase].append(hpath)
            continue
        hbases[hbase] = hpath


def find_cfiles(path, cbases):
    global dict_internal_conflict_cbases  # TODO: Smells?!
    for cfile, cpath in find(path, _RE_CFILE):
        cbase = fn_base(cfile)
        # Detect conflicts among internal dotCs inside a package
        if cbase in cbases:
            if cbase not in dict_internal_conflict_cbases:
                dict_internal_conflict_cbases[cbase] = [cbases[cbase], cpath]
            else:
                dict_internal_conflict_cbases[cbase].append(cpath)
            continue
        cbases[cbase] = cpath


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
                hfiles = find_hfiles_blindly(src_path)
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
    global dict_external_hfiles
    global dict_internal_hfiles
    global dict_pkgs

    dict_external_hfiles = gather_external_hfiles(config.external_groups)

    incomplete_components = IncompleteComponents()
    for group_name, packages in config.internal_groups.items():
        dict_pkgs[group_name] = {}
        for pkg_name, src_paths in packages.items():
            hbases = {}
            cbases = {}
            hfiles = {}
            for src_path in src_paths:
                find_hfiles(src_path, hbases, hfiles)
                find_cfiles(src_path, cbases)

            for hfile, hpath in hfiles.items():
                if hfile not in dict_internal_hfiles:
                    dict_internal_hfiles[hfile] = hpath

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
    global components
    global dict_internal_hfiles
    global dict_pkgs

    assert pkg_name not in dict_pkgs[group_name]
    dict_pkgs[group_name][pkg_name] = []
    paired_components = hbases.viewkeys() & cbases.viewkeys()
    for key in paired_components:
        # Detect cross-package conflicts among internal dotCs
        # In fact, only check between registering components
        # and registered components.
        # For example, suppose both libA/main.cc and libB/main.cpp
        # failed to be registered as a component,
        # the basename conflict between them will be ignored.
        if key in components:  # TODO: Should never happen!
            if key not in dict_internal_conflict_cbases:
                dict_internal_conflict_cbases[key] = [
                    components[key].cpath]
            dict_internal_conflict_cbases[key].append(cbases[key])
        else:
            component = Component(key, hbases[key], cbases[key])
            dict_pkgs[group_name][pkg_name].append(component)
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
        (set internal header files, set external header files, set unknown headers)
    """
    global dict_internal_hfiles
    set_dep_internal_hfiles = set()
    set_dep_external_hfiles = set()
    set_dep_bad_hfiles = set()

    set_current_hfiles = set([header_file])
    while set_current_hfiles:
        set_next_hfiles = set()
        for hfile in set_current_hfiles:
            if hfile in dict_internal_hfiles:
                set_dep_internal_hfiles.add(hfile)
                hpath = dict_internal_hfiles[hfile]
                set_next_hfiles.update(grep_hfiles(hpath))
            elif hfile in dict_external_hfiles:
                set_dep_external_hfiles.add(hfile)
            else:
                # Detect headers failed to locate.
                set_dep_bad_hfiles.add(hfile)
        set_next_hfiles.difference_update(set_dep_internal_hfiles)
        set_next_hfiles.difference_update(set_dep_external_hfiles)
        set_next_hfiles.difference_update(set_dep_bad_hfiles)
        set_current_hfiles = set_next_hfiles

    return (set_dep_internal_hfiles, set_dep_external_hfiles, set_dep_bad_hfiles)


def make_cdep():
    """Determines all hfiles on which a cfile depends.

    Note:
        Simple recursive parsing does not work
        since there may be a cyclic dependency among headers.
    """
    set_bad_hfiles = set()
    dict_hfile_deps = {}
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
            if hfile in dict_external_hfiles:
                component.dep_external_hfiles.add(hfile)
                continue
            if hfile in dict_hfile_deps:
                (set1, set2, set3) = dict_hfile_deps[hfile]
            else:
                (set1, set2, set3) = expand_hfile_deps(hfile)
                dict_hfile_deps[hfile] = (set1, set2, set3)
            component.dep_internal_hfiles.update(set1)
            component.dep_external_hfiles.update(set2)
            set_bad_hfiles.update(set3)
        # Detect indirectly including issues, and non-dependent issues.
        if ind_comp_hfile < 0:
            if comp_hfile in component.dep_internal_hfiles:
                message2 += '%s: does not include %s directly.\n' % (
                    cpath, comp_hfile)
            else:
                message3 += '%s: does not depend on %s.\n' % (
                    cpath, comp_hfile)
    # Report headers failed to locate.
    if set_bad_hfiles:
        print('-' * 80)
        print('warning: failed to locate following headers: ')
        print(' '.join(set_bad_hfiles))
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


def show_hfile_deps(hfile, depth, set_dep_hfiles):
    if hfile in set_dep_hfiles:
        print('+' * depth + '%s (duplicated)' % hfile)
        return
    set_dep_hfiles.add(hfile)
    if hfile in dict_internal_hfiles:
        hpath = dict_internal_hfiles[hfile]
        hbase = fn_base(hfile)
        flag_conflict = ''
        if hbase in dict_internal_conflict_hbases:
            flag_conflict = '*'
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
        print('+' * depth + '%s %s(%s, %s)' %
              (hfile, flag_conflict, hpath, str_component))
        for hfile2 in grep_hfiles(hpath):
            show_hfile_deps(hfile2, depth + 1, set_dep_hfiles)
    elif hfile in dict_external_hfiles:
        print('+' * depth + '%s (in external package %s)' %
              (hfile, '.'.join(dict_external_hfiles[hfile])))
    else:
        print('+' * depth + '%s (failed to locate)' % hfile)


def show_details_of_components():
    """Determines all hfiles on which the specific component depends.

    Very useful for trying to understand
    why a cross-component dependency occurs.
    """
    dict_included_by = {}
    for component in components.values():
        depth = 1
        set_dep_hfiles = set()
        print('-' * 80)
        print('%s (%s in package %s.%s):' %
              (component.name, component.cpath, component.package[0], component.package[1]))
        for hfile in grep_hfiles(component.cpath):
            show_hfile_deps(hfile, depth, set_dep_hfiles)
        for hfile in set_dep_hfiles:
            if hfile in dict_included_by:
                dict_included_by[hfile].append(component.cpath)
            else:
                dict_included_by[hfile] = [component.cpath]
    for hfile in sorted(list(dict_included_by.keys())):
        print('-' * 80)
        print(hfile + ':')
        for cpath in sorted(dict_included_by[hfile]):
            print(' ' + cpath)


def make_ldep():
    """Determines all components on which a component depends."""
    for component in components.values():
        for hfile in component.dep_internal_hfiles:
            assert hfile in dict_internal_hfiles
            hbase = fn_base(hfile)
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
            assert hfile in dict_external_hfiles
            external_pkg = dict_external_hfiles[hfile]
            component.dep_external_pkgs.add(external_pkg)


def output_ldep():
    for group_name in sorted(dict_pkgs.keys()):
        for pkg_name in sorted(dict_pkgs[group_name]):
            print('=' * 80)
            print('pakcage %s.%s dependency:' % (group_name, pkg_name))
            for component in dict_pkgs[group_name][pkg_name]:
                message = '%s -> ' % component.name
                message += ', '.join(sorted(x.name for x in component.dep_components))
                message += '+(external packages) ' + ','.join(
                    sorted('.'.join(x) for x in component.dep_external_pkgs))
                print(message)

"""
create_graph_<range>_<level>
        <range> is one of [all, pkggrp, pkg].
        It indicates those components included in the graph.

        <level> is one of [component, pkg, pkggrp].
        It indicates what a node represents.

Return Value:
        If <level> is "component", return digraph.
        Else return (digraph, dict_edge2deps, dict_node2externalpkgs).
        dict_edge2deps: edge -> list of component direct dependencies
            which been indicated by the edge.
        dict_node2externalpkgs: node -> set of external packages
            on which the node depends.
"""


def create_graph_all_component():
    digraph = nx.DiGraph()
    for component in components.values():
        digraph.add_node(str(component))
        for comp2 in component.dep_components:
            digraph.add_edge(str(component), str(comp2))
    return digraph


def create_graph_all_pkg():
    digraph = nx.DiGraph()
    dict_edge2deps = {}
    dict_node2externalpkgs = {}
    for component in components.values():
        pkg = '.'.join(component.package)
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(pkg)
        if pkg not in dict_node2externalpkgs:
            dict_node2externalpkgs[pkg] = set()
        dict_node2externalpkgs[pkg].update(component.dep_external_pkgs)
        for comp2 in component.dep_components:
            pkg2 = '.'.join(comp2.package)
            if pkg == pkg2:
                continue
            # Duplicated edges between two nodes will be stipped afterwards.
            digraph.add_edge(pkg, pkg2)
            key = (pkg, pkg2)
            if key not in dict_edge2deps:
                dict_edge2deps[key] = []
            dict_edge2deps[key].append((component, comp2))
    return digraph, dict_edge2deps, dict_node2externalpkgs


def create_graph_all_pkggrp():
    digraph = nx.DiGraph()
    dict_edge2deps = {}
    dict_node2externalpkgs = {}
    for component in components.values():
        group_name = component.package[0]
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(group_name)
        if group_name not in dict_node2externalpkgs:
            dict_node2externalpkgs[group_name] = set()
        dict_node2externalpkgs[group_name].update(component.dep_external_pkgs)
        for comp2 in component.dep_components:
            group_name2 = comp2.package[0]
            if group_name == group_name2:
                continue
            # Duplicated edges between two nodes will be stipped afterwards.
            digraph.add_edge(group_name, group_name2)
            key = (group_name, group_name2)
            if key not in dict_edge2deps:
                dict_edge2deps[key] = []
            dict_edge2deps[key].append((component, comp2))
    return digraph, dict_edge2deps, dict_node2externalpkgs


def create_graph_pkggrp_pkg(group_name):
    digraph = nx.DiGraph()
    dict_edge2deps = {}
    dict_node2externalpkgs = {}
    for pkg_name in dict_pkgs[group_name]:
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(pkg_name)
        if pkg_name not in dict_node2externalpkgs:
            dict_node2externalpkgs[pkg_name] = set()
        for component in dict_pkgs[group_name][pkg_name]:
            dict_node2externalpkgs[pkg_name].update(component.dep_external_pkgs)
            for comp2 in component.dep_components:
                (group_name2, pkg_name2) = comp2.package
                if group_name != group_name2 or pkg_name == pkg_name2:
                    continue
                assert group_name == group_name2 and pkg_name != pkg_name2
                # Duplicated edges between two nodes will be stipped
                # afterwards.
                digraph.add_edge(pkg_name, pkg_name2)
                key = (pkg_name, pkg_name2)
                if key not in dict_edge2deps:
                    dict_edge2deps[key] = []
                dict_edge2deps[key].append((component, comp2))
    return digraph, dict_edge2deps, dict_node2externalpkgs


def create_graph_pkg_component(group_name, pkg_name):
    digraph = nx.DiGraph()
    package = (group_name, pkg_name)
    for component in dict_pkgs[group_name][pkg_name]:
        digraph.add_node(str(component))
        for comp2 in component.dep_components:
            package2 = comp2.package
            if package2 != package:
                continue
            digraph.add_edge(str(component), str(comp2))
    return digraph


def output_original_graph_info(dict_edge2deps, dict_node2externalpkgs):
    print('=' * 80)
    print('each edge in the original graph logically consists of '
          'some cross-component dependencies:')
    for item in dict_edge2deps.items():
        message = '->'.join(item[0]) + ': '
        num_deps = 5 if len(item[1]) > 5 else len(item[1])
        message += ' '.join(str(x[0]) + '->' + str(x[1])
                            for x in item[1][0:num_deps])
        if num_deps < len(item[1]):
            message += ' ...'
        print(message)
    print('=' * 80)
    print('each node in the original graph depends on some external packages:')
    for item in dict_node2externalpkgs.items():
        print(str(item[0]) + ': ' +
              ' '.join('.'.join(x) for x in list(item[1])))


def calculate_graph(digraph, dot_basename=None):
    size_graph = digraph.number_of_nodes()
    if size_graph == 0:
        return
    if dot_basename:
        write_dot(digraph, dot_basename + '_orig.dot')
    key_node = str

    def key_edge(x):
        return str(x[0]) + '->' + str(x[1])

    (cycles, dict_node2cycle) = make_dag(digraph, key_node)
    (layers, dict_layer_no, redundant_edges) = layering_dag(digraph, key_node)
    (ccd, dict_cd) = calc_ccd(digraph, cycles, layers)
    print('=' * 80)
    print('cycles detected(%d cycles): ' % len(cycles))
    for min_node in sorted(cycles.keys(), key=str):
        cycle = cycles[min_node]
        message = '[cycle]%s nodes(%d nodes): ' % (
            str(min_node), cycle.number_of_nodes())
        message += ' '.join(sorted(map(key_node, cycle.nodes())))
        print(message)
        message = '[cycle]%s edges(%d edges): ' % (
            str(min_node), cycle.number_of_edges())
        message += ' '.join(sorted(map(key_edge, cycle.edges())))
        print(message)
    print('=' * 80)
    print('layers(%d layers):' % len(layers))

    def repr_node(node):
        cycle_key = dict_node2cycle[node]
        if cycle_key:
            assert node == cycle_key
            str_node = '[cycle]' + str(node)
        else:
            str_node = str(node)
        return str_node

    for i, layer in enumerate(layers):
        print('layer %d(%d nodes): ' % (i, len(layer)))
        for node in layer:
            message = repr_node(node) + ' -> '
            message += ' '.join(sorted(map(repr_node,
                                           digraph.successors(node))))
            print(message)

    print('redundant edges stripped(%d edges): ' % len(redundant_edges))
    print(' '.join(sorted(map(key_edge, redundant_edges))))
    # CCD_fullBTree = (N+1)*log2(N+1)-N
    # ACD = CCD/N
    # NCCD = CCD/CCD_fullBTree
    acd = ccd / size_graph
    ccd_full_btree = (size_graph + 1) * \
        (math.log(size_graph + 1, 2)) - size_graph
    nccd = ccd / ccd_full_btree
    print('=' * 80)
    print('SUMMARY:')
    print('Nodes: %d\t Cycles: %d\t Layers: %d' %
          (size_graph, len(cycles), len(layers)))
    print('CCD: %d\t ACCD: %f\t NCCD: %f(typical range is [0.85, 1.10])' %
          (ccd, acd, nccd))
    if dot_basename:
        if cycles:
            g = nx.DiGraph()
            for cycle in cycles.values():
                g.add_edges_from(cycle.edges_iter())
            write_dot(g, dot_basename + '_cycles.dot')
        write_dot(digraph, dot_basename + '_final.dot')


def main():
    parser = ap.ArgumentParser(description=__doc__)

    parser.add_argument('-f', '--conf', dest='path_conf', default='cppdep.xml',
                        help="""an XML file which describes
                        the source code structure of a C/C++ project""")

    parser.add_argument('-d', '--debug', dest='details_of_components',
                        action='store_true', default=False,
                        help="""show all warnings and details
                        of every component (aka. includes/included by),
                        but not analyze dependencies.""")

    args = parser.parse_args()

    time_start = time.time()
    config = Config(args.path_conf)
    make_components(config)

    make_cdep()

    if args.details_of_components:
        show_details_of_components()
        print('analyzing done in %f minutes.' %
              ((time.time() - time_start) / 60))
    make_ldep()

    print('@' * 80)
    print('analyzing dependencies among all components ...')
    digraph = create_graph_all_component()
    calculate_graph(digraph)

    print('@' * 80)
    print('analyzing dependencies among all packages ...')
    digraph, dict_edge2deps, dict_node2externalpkgs = create_graph_all_pkg()
    output_original_graph_info(dict_edge2deps, dict_node2externalpkgs)
    calculate_graph(digraph, 'all_packages')

    print('@' * 80)
    print('analyzing dependencies among all package groups ...')
    digraph, dict_edge2deps, dict_node2externalpkgs = create_graph_all_pkggrp()
    output_original_graph_info(dict_edge2deps, dict_node2externalpkgs)
    calculate_graph(digraph, 'all_pkggrps')

    for group_name in dict_pkgs:
        print('@' * 80)
        print('analyzing dependencies among packages in ' +
              'the specified package group %s ...' % group_name)
        digraph, dict_edge2deps, dict_node2externalpkgs = \
            create_graph_pkggrp_pkg(group_name)
        output_original_graph_info(dict_edge2deps, dict_node2externalpkgs)
        calculate_graph(digraph, group_name)

    for group_name in dict_pkgs:
        for pkg_name in dict_pkgs[group_name]:
            print('@' * 80)
            print('analyzing dependencies among components in ' +
                  'the specified pakcage %s.%s ...' % (group_name, pkg_name))
            digraph = create_graph_pkg_component(group_name, pkg_name)
            calculate_graph(digraph, group_name + '.' + pkg_name)

    print('analyzing done in %f minutes.' % ((time.time() - time_start) / 60))

if __name__ == '__main__':
    try:
        main()
    except IOError as err:
        print("IO Error:\n" + str(err))
        sys.exit(1)
    except ConfigXmlParseError as err:
        print("Configuration XML Error:\n" + str(err))
        sys.exit(1)
