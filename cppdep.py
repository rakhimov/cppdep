#!/usr/bin/env python

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


_RE_HFILE = re.compile(r'(?i).*\.h(xx|\+\+|h|pp|)$')
_RE_CFILE = re.compile(r'(?i).*\.c(xx|\+\+|c|pp|)$')


def find(path, fnmatcher):
    if os.path.isfile(path):
        fn = os.path.basename(path)
        m = fnmatcher.match(fn)
        if m:
            yield fn, path
        return
    for root, dirs, files in os.walk(path):
        for entry in files:
            m = fnmatcher.match(entry)
            if m:
                full_path = os.path.join(root, entry)
                yield entry, full_path


def find_hfiles_blindly(path):
    return [hfile for hfile, _ in find(path, _RE_HFILE)]


class Component(object):

    def __init__(self, name, hpath, cpath):
        self.package = ('anonymous', 'anonymous')
        self.name = name
        self.hpath = hpath
        self.cpath = cpath
        self.dep_our_hfiles = set()
        self.dep_outside_hfiles = set()
        self.dep_comps = set()
        self.dep_outside_pkgs = set()

    def __str__(self):
        return self.name

# Following two global variables are initialized by parse_conf().
dict_outside_conf = dict()
dict_our_conf = dict()

dict_outside_hfiles = dict()
dict_our_hfiles = dict()
dict_our_hbases = dict()
dict_our_conflict_hbases = dict()
dict_our_outside_conflict_hfiles = dict()
dict_our_conflict_cbases = dict()
dict_pkgs = dict()
dict_comps = dict()


def find_hfiles(path, hbases, hfiles):
    for hfile, hpath in find(path, _RE_HFILE):
        # Detect conflicts among our headers inside a package
        if hfile not in hfiles:
            hfiles[hfile] = hpath
        hbase = fn_base(hfile)
        # Detect conflicts among our headers inside a package
        if hbase in hbases:
            if hbase not in dict_our_conflict_hbases:
                dict_our_conflict_hbases[hbase] = [hbases[hbase]]
            dict_our_conflict_hbases[hbase].append(hpath)
            continue
        hbases[hbase] = hpath


def find_cfiles(path, cbases):
    for (cfile, cpath) in find(path, _RE_CFILE):
        cbase = fn_base(cfile)
        # Detect conflicts among our dotCs inside a package
        if cbase in cbases:
            if cbase not in dict_our_conflict_cbases:
                dict_our_conflict_cbases[cbase] = [cbases[cbase], cpath]
            else:
                dict_our_conflict_cbases[cbase].append(cpath)
            continue
        cbases[cbase] = cpath


def parse_conf_package_group(pkg_group, dict_conf):
    """Parses the body of <package-group/> in XML config file.

    Args:
        pkg_group: The <package-group> XML element.
        dict_conf: The destination configuration dictionary for configurations.

    Raises:
        ConfigXmlParseError: Invalid configuration or parsing error.
    """
    group_name = pkg_group.get('name')
    group_path = pkg_group.get('path')
    dict_conf[group_name] = dict()

    for pkg in pkg_group.findall('package'):
        pkg_name = pkg.get('name')
        src_paths = pkg.text.strip().split()
        dict_conf[group_name][pkg_name] = \
            [os.path.normpath(os.path.join(group_path, x)) for x in src_paths]

    for pkg_path in pkg_group.text.strip().split():
        pkg_path = os.path.normpath(os.path.join(group_path, pkg_path))
        pkg_name = os.path.basename(pkg_path)
        dict_conf[group_name][pkg_name] = [pkg_path]

    for pkg_path in dict_conf[group_name][pkg_name]:
        if not os.path.exists(pkg_path):
            raise ConfigXmlParseError("""detected a config error for package
                                         %s.%s: %s does not exist!""" %
                                      (group_name, pkg_name, pkg_path))


def parse_conf(path_conf):
    """Parses the XML configuration file.

    Raises:
        ConfigXmlParseError: The configuration or XML is invalid.
    """
    global dict_outside_conf
    global dict_our_conf
    root = ElementTree.parse(path_conf).getroot()
    for pkg_group in root.findall('package-group'):
        attr_outside = pkg_group.get('outside')
        is_outside = attr_outside and attr_outside.lower() == 'true'
        dict_conf = dict_outside_conf if is_outside else dict_our_conf
        parse_conf_package_group(pkg_group, dict_conf)


def make_components():
    """pair hfiles and cfiles."""
    global dict_outside_hfiles
    global dict_our_hfiles
    global dict_our_hbases
    global dict_pkgs
    global dict_comps
    for group_name in dict_outside_conf:
        for pkg_name in dict_outside_conf[group_name]:
            pkg = (group_name, pkg_name)
            for src_path in dict_outside_conf[group_name][pkg_name]:
                hfiles = find_hfiles_blindly(src_path)
                for hfile in hfiles:
                    dict_outside_hfiles[hfile] = pkg
    hbases = dict()
    hfiles = dict()
    cbases = dict()
    message = ''
    for group_name in dict_our_conf:
        dict_pkgs[group_name] = dict()
        for pkg_name in dict_our_conf[group_name]:
            dict_pkgs[group_name][pkg_name] = list()
            hbases.clear()
            hfiles.clear()
            cbases.clear()
            for src_path in dict_our_conf[group_name][pkg_name]:
                find_hfiles(src_path, hbases, hfiles)
                find_cfiles(src_path, cbases)
            # Detect cross-package conflicts among our headers
            for hbase in list(hbases.keys()):
                if hbase in dict_our_hbases:
                    if hbase not in dict_our_conflict_hbases:
                        dict_our_conflict_hbases[hbase] = [
                            dict_our_hbases[hbase]]
                    dict_our_conflict_hbases[hbase].append(hbases[hbase])
                    del hbases[hbase]
            for hfile in list(hfiles.keys()):
                if hfile in dict_our_hfiles:
                    del hfiles[hfile]
            dict_our_hfiles.update(hfiles)
            dict_our_hbases.update(hbases)
            for key in list(cbases.keys()):
                if key in hbases:
                    # Detect cross-package conflicts among our dotCs
                    # In fact, only check between registering components
                    # and registered components.
                    # For example, suppose both libA/main.cc and libB/main.cpp
                    # failed to be registered as a component,
                    # the basename conflict between them will be ignored.
                    if key in dict_comps:
                        if key not in dict_our_conflict_cbases:
                            dict_our_conflict_cbases[key] = [
                                dict_comps[key].cpath]
                        dict_our_conflict_cbases[key].append(cbases[key])
                    else:
                        comp = Component(key, hbases[key], cbases[key])
                        dict_pkgs[group_name][pkg_name].append(comp)
                        comp.package = (group_name, pkg_name)
                        dict_comps[key] = comp
                    del hbases[key]
                    del cbases[key]
            # Detect files failed to associated with any component
            if len(hbases) or len(cbases):
                message += 'in package %s.%s: ' % (group_name, pkg_name)
                if len(hbases):
                    message += ', '.join(map(os.path.basename,
                                             hbases.values()))
                if len(cbases):
                    message += ' ' + \
                        ', '.join(map(os.path.basename, cbases.values()))
                message += '\n'
    # Report files failed to associated with any component
    if message:
        print('-' * 80)
        print('warning: detected files failed to associate '
              'with any component (all will be ignored): ')
        print(message)
    # Report conflicts among our headers
    if len(dict_our_conflict_hbases):
        message = 'warning: detected file basename conflicts among our ' + \
                  'headers (all except the first one will be ignored):\n'
        for hbase in dict_our_conflict_hbases:
            message += '%s: ' % hbase
            for hpath in dict_our_conflict_hbases[hbase]:
                digest = md5sum(hpath)
                message += '%s(%s) ' % (hpath, digest)
            message += '\n'
        print('-' * 80)
        print(message)
    # Report conflicts among our dotCs
    if len(dict_our_conflict_cbases):
        message = 'warning: detected file basename conflicts among our ' + \
                  'dotCs (all except the first one will be ignored):\n'
        for cbase in dict_our_conflict_cbases:
            message += '%s: ' % cbase
            for cpath in dict_our_conflict_cbases[cbase]:
                digest = md5sum(cpath)
                message += '%s(%s) ' % (cpath, digest)
            message += '\n'
        print('-' * 80)
        print(message)
    # Detect and report conflicts between outside and our headers
    set_outside_hfiles = set(dict_outside_hfiles.keys())
    set_our_hfiles = set(dict_our_hfiles.keys())
    set_common_hfiles = set_our_hfiles.intersection(set_outside_hfiles)
    if len(set_common_hfiles):
        message = 'warning: detected file name conflicts between our and ' + \
                  'outside headers (outside ones will be ignored): \n'
        for hfile in set_common_hfiles:
            message += '%s (in outside package %s): %s\n' % \
                       (hfile, '.'.join(dict_outside_hfiles[hfile]),
                        dict_our_hfiles[hfile])
        print('-' * 80)
        print(message)
        del dict_outside_hfiles[hfile]


def expand_hfile_deps(hfile):
    set_dep_our_hfiles = set()
    set_dep_outside_hfiles = set()
    set_dep_bad_hfiles = set()
    set_current_hfiles = set([hfile])
    set_next_hfiles = set()
    while True:
        for hfile in set_current_hfiles:
            if hfile in dict_our_hfiles:
                set_dep_our_hfiles.add(hfile)
                hpath = dict_our_hfiles[hfile]
                set_next_hfiles.update(grep_hfiles(hpath))
            elif hfile in dict_outside_hfiles:
                set_dep_outside_hfiles.add(hfile)
            else:
                # Detect headers failed to locate.
                set_dep_bad_hfiles.add(hfile)
        set_next_hfiles.difference_update(set_dep_our_hfiles)
        set_next_hfiles.difference_update(set_dep_outside_hfiles)
        set_next_hfiles.difference_update(set_dep_bad_hfiles)
        if not set_next_hfiles:
            break
        set_current_hfiles, set_next_hfiles = set_next_hfiles, set_current_hfiles
        set_next_hfiles.clear()
    return (set_dep_our_hfiles, set_dep_outside_hfiles, set_dep_bad_hfiles)


def make_cdep():
    """Determines all hfiles on which a cfile depends.

    Note:
        Simple recursive parsing does not work
        since there may be a cyclic dependency among headers.
    """
    set_bad_hfiles = set()
    dict_hfile_deps = dict()
    message = ''
    message2 = ''
    message3 = ''
    for comp in dict_comps.values():
        cpath = comp.cpath
        hfiles = grep_hfiles(cpath)
        if len(hfiles) == 0:
            continue
        comp_hfile = os.path.basename(comp.hpath)
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
            if hfile in dict_outside_hfiles:
                comp.dep_outside_hfiles.add(hfile)
                continue
            if hfile in dict_hfile_deps:
                (set1, set2, set3) = dict_hfile_deps[hfile]
            else:
                (set1, set2, set3) = expand_hfile_deps(hfile)
                dict_hfile_deps[hfile] = (set1, set2, set3)
            comp.dep_our_hfiles.update(set1)
            comp.dep_outside_hfiles.update(set2)
            set_bad_hfiles.update(set3)
        # Detect indirectly including issues, and non-dependent issues.
        if ind_comp_hfile < 0:
            if comp_hfile in comp.dep_our_hfiles:
                message2 += '%s: does not include %s directly.\n' % (
                    cpath, comp_hfile)
            else:
                message3 += '%s: does not depend on %s.\n' % (
                    cpath, comp_hfile)
    # Report headers failed to locate.
    if len(set_bad_hfiles) != 0:
        print('-' * 80)
        print('warning: failed to locate following headers: ')
        print(' '.join(set_bad_hfiles))
    # Report non-dependent issues.
    if len(message3):
        print('-' * 80)
        print('warning: following every dotC does not depend on ' +
              'its associated header: ')
        print(message3)
    # Report indirectly including issues.
    if len(message2):
        print('-' * 80)
        print('warning: following every dotC does not include ' +
              'its associated header directly: ')
        print(message2)
    # Report first header issues.
    if len(message):
        print('-' * 80)
        print('warning: following every dotC does not include ' +
              'its associated header before other headers: ')
        print(message)


def show_hfile_deps(hfile, depth, set_dep_hfiles):
    if hfile in set_dep_hfiles:
        print('+' * depth + '%s (duplicated)' % hfile)
        return
    set_dep_hfiles.add(hfile)
    if hfile in dict_our_hfiles:
        hpath = dict_our_hfiles[hfile]
        hbase = fn_base(hfile)
        flag_conflict = ''
        if (hbase in dict_our_conflict_hbases or
                hfile in dict_our_outside_conflict_hfiles):
            flag_conflict = '*'
        str_comp = None
        if hbase in dict_comps:
            comp = dict_comps[hbase]
            if os.path.basename(comp.hpath) == hfile:
                str_comp = 'associates with %s in %s.%s' % (
                    comp.name, comp.package[0], comp.package[1])
            else:
                str_comp = 'basename conflicts with %s in %s.%s' % (
                    comp.name, comp.package[0], comp.package[1])
        else:
            str_comp = 'does not associate with any component'
        print('+' * depth + '%s %s(%s, %s)' %
              (hfile, flag_conflict, hpath, str_comp))
        for hfile2 in grep_hfiles(hpath):
            show_hfile_deps(hfile2, depth + 1, set_dep_hfiles)
    elif hfile in dict_outside_hfiles:
        print('+' * depth + '%s (in outside package %s)' %
              (hfile, '.'.join(dict_outside_hfiles[hfile])))
    else:
        print('+' * depth + '%s (failed to locate)' % hfile)


def show_details_of_comps():
    """Determines all hfiles on which the specific component depends.

    Very useful for trying to understand
    why a cross-component dependency occurs.
    """
    dict_included_by = dict()
    for comp in dict_comps.values():
        depth = 1
        set_dep_hfiles = set()
        print('-' * 80)
        print('%s (%s in package %s.%s):' %
              (comp.name, comp.cpath, comp.package[0], comp.package[1]))
        for hfile in grep_hfiles(comp.cpath):
            show_hfile_deps(hfile, depth, set_dep_hfiles)
        for hfile in set_dep_hfiles:
            if hfile in dict_included_by:
                dict_included_by[hfile].append(comp.cpath)
            else:
                dict_included_by[hfile] = [comp.cpath]
    for hfile in sorted(list(dict_included_by.keys())):
        print('-' * 80)
        print(hfile + ':')
        for cpath in sorted(dict_included_by[hfile]):
            print(' ' + cpath)


def make_ldep():
    """Determines all components on which a component depends."""
    for comp in dict_comps.values():
        for hfile in comp.dep_our_hfiles:
            assert hfile in dict_our_hfiles
            hbase = fn_base(hfile)
            if hbase in dict_comps:
                comp2 = dict_comps[hbase]
                # We've reported hfile basename conflicts at make_components().
                if comp2 != comp and os.path.basename(comp2.hpath) == hfile:
                    comp.dep_comps.add(comp2)
            else:
                # This our header doesn't belong to any component. We've ever
                # warned it at make_components().
                pass
        for hfile in comp.dep_outside_hfiles:
            assert hfile in dict_outside_hfiles
            outside_pkg = dict_outside_hfiles[hfile]
            comp.dep_outside_pkgs.add(outside_pkg)


def output_ldep():
    for group_name in sorted(dict_pkgs.keys()):
        for pkg_name in sorted(dict_pkgs[group_name]):
            print('=' * 80)
            print('pakcage %s.%s dependency:' % (group_name, pkg_name))
            for comp in dict_pkgs[group_name][pkg_name]:
                message = '%s -> ' % comp.name
                message += ', '.join(sorted(x.name for x in comp.dep_comps))
                message += '+(outside packages) ' + ','.join(
                    sorted('.'.join(x) for x in comp.dep_outside_pkgs))
                print(message)

"""
create_graph_<range>_<level>
        <range> is one of [all, pkggrp, pkg].
        It indicates those components included in the graph.

        <level> is one of [comp, pkg, pkggrp].
        It indicates what a node represents.

Return Value:
        If <level> is "comp", return digraph.
        Else return (digraph, dict_edge2deps, dict_node2outsidepkgs).
        dict_edge2deps: edge -> list of component direct dependencies
            which been indicated by the edge.
        dict_node2outsidepkgs: node -> set of outside packages
            on which the node depends.
"""


def create_graph_all_comp():
    digraph = nx.DiGraph()
    for comp in dict_comps.values():
        digraph.add_node(str(comp))
        for comp2 in comp.dep_comps:
            digraph.add_edge(str(comp), str(comp2))
    return digraph


def create_graph_all_pkg():
    digraph = nx.DiGraph()
    dict_edge2deps = dict()
    dict_node2outsidepkgs = dict()
    for comp in dict_comps.values():
        pkg = '.'.join(comp.package)
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(pkg)
        if pkg not in dict_node2outsidepkgs:
            dict_node2outsidepkgs[pkg] = set()
        dict_node2outsidepkgs[pkg].update(comp.dep_outside_pkgs)
        for comp2 in comp.dep_comps:
            pkg2 = '.'.join(comp2.package)
            if pkg == pkg2:
                continue
            # Duplicated edges between two nodes will be stipped afterwards.
            digraph.add_edge(pkg, pkg2)
            key = (pkg, pkg2)
            if key not in dict_edge2deps:
                dict_edge2deps[key] = list()
            dict_edge2deps[key].append((comp, comp2))
    return digraph, dict_edge2deps, dict_node2outsidepkgs


def create_graph_all_pkggrp():
    digraph = nx.DiGraph()
    dict_edge2deps = dict()
    dict_node2outsidepkgs = dict()
    for comp in dict_comps.values():
        group_name = comp.package[0]
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(group_name)
        if group_name not in dict_node2outsidepkgs:
            dict_node2outsidepkgs[group_name] = set()
        dict_node2outsidepkgs[group_name].update(comp.dep_outside_pkgs)
        for comp2 in comp.dep_comps:
            group_name2 = comp2.package[0]
            if group_name == group_name2:
                continue
            # Duplicated edges between two nodes will be stipped afterwards.
            digraph.add_edge(group_name, group_name2)
            key = (group_name, group_name2)
            if key not in dict_edge2deps:
                dict_edge2deps[key] = list()
            dict_edge2deps[key].append((comp, comp2))
    return digraph, dict_edge2deps, dict_node2outsidepkgs


def create_graph_pkggrp_pkg(group_name):
    digraph = nx.DiGraph()
    dict_edge2deps = dict()
    dict_node2outsidepkgs = dict()
    for pkg_name in dict_pkgs[group_name]:
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(pkg_name)
        if pkg_name not in dict_node2outsidepkgs:
            dict_node2outsidepkgs[pkg_name] = set()
        for comp in dict_pkgs[group_name][pkg_name]:
            dict_node2outsidepkgs[pkg_name].update(comp.dep_outside_pkgs)
            for comp2 in comp.dep_comps:
                (group_name2, pkg_name2) = comp2.package
                if group_name != group_name2 or pkg_name == pkg_name2:
                    continue
                assert group_name == group_name2 and pkg_name != pkg_name2
                # Duplicated edges between two nodes will be stipped
                # afterwards.
                digraph.add_edge(pkg_name, pkg_name2)
                key = (pkg_name, pkg_name2)
                if key not in dict_edge2deps:
                    dict_edge2deps[key] = list()
                dict_edge2deps[key].append((comp, comp2))
    return digraph, dict_edge2deps, dict_node2outsidepkgs


def create_graph_pkg_comp(group_name, pkg_name):
    digraph = nx.DiGraph()
    package = (group_name, pkg_name)
    for comp in dict_pkgs[group_name][pkg_name]:
        digraph.add_node(str(comp))
        for comp2 in comp.dep_comps:
            package2 = comp2.package
            if package2 != package:
                continue
            digraph.add_edge(str(comp), str(comp2))
    return digraph


def output_original_graph_info(dict_edge2deps, dict_node2outsidepkgs):
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
    print('each node in the original graph depends on some outside packages:')
    for item in dict_node2outsidepkgs.items():
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
    print('CCD: %d\t ACCD: %f\t NCCD: %f(typical range is [0.85, 1.10])' % (
        ccd, acd, nccd))
    if dot_basename:
        if len(cycles):
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

    parser.add_argument('-d', '--debug', dest='details_of_comps',
                        action='store_true', default=False,
                        help="""show all warnings and details
                        of every component (aka. includes/included by),
                        but not analyze dependencies.""")

    args = parser.parse_args()

    time_start = time.time()
    parse_conf(args.path_conf)

    make_components()

    make_cdep()

    if args.details_of_comps:
        show_details_of_comps()
        time_end = time.time()
        print('analyzing done in %s minutes.' %
              str((time_end - time_start) / 60))
    make_ldep()

    print('@' * 80)
    print('analyzing dependencies among all components ...')
    digraph = create_graph_all_comp()
    calculate_graph(digraph)

    print('@' * 80)
    print('analyzing dependencies among all packages ...')
    digraph, dict_edge2deps, dict_node2outsidepkgs = create_graph_all_pkg()
    output_original_graph_info(dict_edge2deps, dict_node2outsidepkgs)
    calculate_graph(digraph, 'all_packages')

    print('@' * 80)
    print('analyzing dependencies among all package groups ...')
    digraph, dict_edge2deps, dict_node2outsidepkgs = create_graph_all_pkggrp()
    output_original_graph_info(dict_edge2deps, dict_node2outsidepkgs)
    calculate_graph(digraph, 'all_pkggrps')

    for group_name in dict_pkgs:
        print('@' * 80)
        print('analyzing dependencies among packages in ' +
              'the specified package group %s ...' % group_name)
        digraph, dict_edge2deps, dict_node2outsidepkgs = \
            create_graph_pkggrp_pkg(group_name)
        output_original_graph_info(dict_edge2deps, dict_node2outsidepkgs)
        calculate_graph(digraph, group_name)

    for group_name in dict_pkgs:
        for pkg_name in dict_pkgs[group_name]:
            print('@' * 80)
            print('analyzing dependencies among components in ' +
                  'the specified pakcage %s.%s ...' % (group_name, pkg_name))
            digraph = create_graph_pkg_comp(group_name, pkg_name)
            calculate_graph(digraph, group_name + '.' + pkg_name)

    time_end = time.time()
    print('analyzing done in %s minutes.' % str((time_end - time_start) / 60))

if __name__ == '__main__':
    try:
        main()
    except IOError as err:
        print("IO Error:\n" + str(err))
        sys.exit(1)
    except ConfigXmlParseError as err:
        print("Configuration XML Error:\n" + str(err))
        sys.exit(1)
