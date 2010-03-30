#!/usr/bin/env python

'''
This a rewrite of dep_utils(adep/cdep/ldep) mentioned at the book of Large-Scale C++ Software Design.
The location of dep_utils source code mentioned at the book is outdated and I only find a copy of it (via Google) at http://www-numi.fnal.gov/computing/d120/releases/R2.2/Dependency/.

Differences to original dep_utils:
1) More maintainable. Rewite in Python.
2) Easier to use. Only one simple XML config file need. Unified adep/dep/cdep into one.
3) Remove file alias support since the file name length limitation is much relax the 20 years ago.
4) Add support of multiple package groups and packages

The objective of this tool is to detect following cases in source code:
1) unmatched dotH and dotC.
2) the first docH inclued in the dotC doesn't belong to the component.
3) Some dotH included directly or indirectly don't exist.
4) cycle dependencies among components/packages/package groups.

Each of them is considered as a quality flaw and should be removed by revising the code.

BUGS:
1) Can not detect dependency indicated by declarations of global variable or function such as "extern int printf();".

Features TODO:
1) Add support to Graphviz output

Dependencies of this tool:
1) Python 2.6
2) NetworkX from http://networkx.lanl.gov/.
'''

import sys
import os.path
import re
import hashlib
import math
import time
# ElementTree is introduced in by Python 2.5.
from xml.etree import ElementTree

import networkx as nx
from networkx_ext import *

def md5sum(fpath):
    m = hashlib.md5()
    f = open(fpath, 'rb')
    m.update(f.read())
    f.close()
    return m.digest()

def fn_base(fn):
    return os.path.splitext(fn)[0]

def grep(pattern, file_obj):
    grepper = re.compile(pattern)
    for line_num, line in enumerate(file_obj):
        m = grepper.search(line)
        if m:
            yield (line_num, line, m)

def grep_hfiles(src_file):
    hfiles = list()
    #f = open(src_file, encoding='iso8859-1')
    f = open(src_file, 'rb')
    for elem in grep(b'^\s*#include\s*(<(?P<hfile>.+)>|"(?P<hfile2>.+)")\s*', f):
        m = elem[2]
        if(m.group('hfile')):
            hfile = m.group('hfile')
        else:
            hfile = m.group('hfile2')
        hfiles.append(os.path.basename(hfile))
    f.close()
    return hfiles

def find(path, file_name):
    fnmatcher = re.compile(file_name)
    for root,dirs,files in os.walk(path):
        for entry in files:
            m = fnmatcher.match(entry)
            if m:
                full_path = os.path.join(root, entry)
                yield (entry, full_path)

def find_hfiles_blindly(path):
    hfiles = list()
    file_name = '(?i).*\.h(xx|\+\+|h|pp|)$'
    for (hfile,hpath) in find(path, file_name):
        hfiles.append(hfile)
    return hfiles

def find_hfiles(path):
    hfiles = dict()
    hbases = dict()
    patt_fn = '(?i).*\.h(xx|\+\+|h|pp|)$'
    for (hfile,hpath) in find(path, patt_fn):
        hfiles[hfile] = hpath
        hbase = fn_base(hfile)
        if(hbase in hbases):
            warn_fnbase_conflict(hbases[hbase], hpath)
        hbases[hbase] = hpath
    return (hbases, hfiles)

def find_cfiles(path):
    cbases = dict()
    patt_fn = '(?i).*\.c(xx|\+\+|c|pp|)$'
    for (cfile,cpath) in find(path, patt_fn):
        cbase = fn_base(cfile)
        if(cbase in cbases):
            warn_fnbase_conflict(cbases[cbase], cpath)
        cbases[cbase] = cpath
    return cbases

class component(object):
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
dict_pkgs  = dict()
dict_comps = dict()

def parse_conf():
    global dict_outside_conf
    global dict_our_conf
    root = ElementTree.parse('dep_conf.xml').getroot()
    for pkg_group in root.findall('outside_package_group'):
        group_name = pkg_group.get('name')
        group_path = pkg_group.get('path')
        dict_outside_conf[group_name] = dict()
        for pkg in pkg_group.findall('package'):
            pkg_name = pkg.get('name')
            inc_paths = pkg.text.strip().split()
            inc_paths = map(lambda x: os.path.normpath(os.path.join(group_path, x)), inc_paths)
            dict_outside_conf[group_name][pkg_name] = inc_paths
    for pkg_group in root.findall('our_package_group'):
        group_name = pkg_group.get('name')
        group_path = pkg_group.get('path')
        dict_our_conf[group_name] = dict()
        for pkg_path in pkg_group.text.strip().split():
            pkg_path = os.path.normpath(os.path.join(group_path, pkg_path))
            pkg_name = os.path.basename(pkg_path)
            dict_our_conf[group_name][pkg_name] = pkg_path

def warn_fnbase_conflict(path1, path2):
    digest1 = md5sum(path1)
    digest2 = md5sum(path2)
    if(digest1==digest2):
        same_diff = 'same'
    else:
        same_diff = 'different'
    print 'warning: a file-basename conflict detected(%s content): %s, %s'%(same_diff, path1, path2)

def make_components():
    '''pair hfiles and cfiles.'''
    global dict_outside_hfiles
    global dict_our_hfiles
    global dict_our_hbases
    global dict_pkgs
    global dict_comps
    for group_name in dict_outside_conf:
        for pkg_name in dict_outside_conf[group_name]:
            pkg = (group_name, pkg_name)
            for inc_path in dict_outside_conf[group_name][pkg_name]:
                hfiles = find_hfiles_blindly(inc_path)
                for hfile in hfiles:
                    dict_outside_hfiles[hfile] = pkg
    for group_name in dict_our_conf:
        dict_pkgs[group_name] = dict()
        for pkg_name in dict_our_conf[group_name]:
            pkg_path = dict_our_conf[group_name][pkg_name]
            dict_pkgs[group_name][pkg_name] = list()
            hbases, hfiles = find_hfiles(pkg_path)
            cbases = find_cfiles(pkg_path)
            for key in hbases.keys():
                if(key in dict_our_hbases):
                    warn_fnbase_conflict(dict_our_hbases[key], hbases[key])
            dict_our_hfiles.update(hfiles)
            dict_our_hbases.update(hbases)
            keys = list(cbases.keys())
            for key in keys:
                if(key in hbases):
                    comp = component(key, hbases[key], cbases[key])
                    dict_pkgs[group_name][pkg_name].append(comp)
                    comp.package = (group_name, pkg_name)
                    dict_comps[key] = comp
                    del hbases[key]
                    del cbases[key]
            if(len(hbases) or len(cbases)):
                message = 'warning: failed to put follow files into any components (in package %s.%s): '%(group_name, pkg_name)
                if(len(hbases)):
                    message += ', '.join(map(os.path.basename, hbases.values()))
                if(len(cbases)):
                    message += ', '.join(map(os.path.basename, cbases.values()))
                print message

def expand_hfile_deps(hfile):
    set_dep_our_hfiles = set()
    set_dep_outside_hfiles = set()
    set_dep_bad_hfiles = set()
    set_current_hfiles = set([hfile])
    set_next_hfiles = set()
    while(1):
        for hfile in set_current_hfiles:
            if(hfile in dict_our_hfiles):
                set_dep_our_hfiles.add(hfile)
                hpath = dict_our_hfiles[hfile]
                set_next_hfiles.update(grep_hfiles(hpath))
            elif(hfile in dict_outside_hfiles):
                set_dep_outside_hfiles.add(hfile)
            else:
                set_dep_bad_hfiles.add(hfile)
        set_next_hfiles.difference_update(set_dep_our_hfiles)
        set_next_hfiles.difference_update(set_dep_outside_hfiles)
        set_next_hfiles.difference_update(set_dep_bad_hfiles)
        if(len(set_next_hfiles)==0):
            break
        set_current_hfiles, set_next_hfiles = set_next_hfiles, set_current_hfiles
        set_next_hfiles.clear()
    return (set_dep_our_hfiles, set_dep_outside_hfiles, set_dep_bad_hfiles)

def make_cdep():
    '''determine all hfiles on which a cfile depends.
    Note: Recursively parsing does not work since there may be a cycle dependency among headers.'''
    set_bad_hfiles = set()
    dict_hfile_deps = dict()
    for item in dict_comps.items():
        key = item[0]
        comp = item[1]
        cpath = comp.cpath
        #print 'cpath: %s'%cpath
        hfiles = grep_hfiles(cpath)
        if(len(hfiles)==0):
            continue
        hfile = os.path.basename(comp.hpath)
        if(hfiles[0]!=hfile):
            print 'warning: the first header of %s is %s, but %s expected.'%(cpath, hfiles[0], hfile)
        for hfile in hfiles:
            if(hfile in dict_outside_hfiles):
                comp.dep_outside_hfiles.add(hfile)
                continue
            if(hfile in dict_hfile_deps):
                (set1, set2, set3) = dict_hfile_deps[hfile]
            else:
                (set1, set2, set3) = expand_hfile_deps(hfile)
                dict_hfile_deps[hfile] = (set1, set2, set3)
            comp.dep_our_hfiles.update(set1)
            comp.dep_outside_hfiles.update(set2)
            set_bad_hfiles.update(set3)
    if(len(set_bad_hfiles)!=0):
        print 'warning: failed to locate following headers when analyzing compilation dependencies: ', ' '.join(set_bad_hfiles)

def make_ldep():
    '''determine all components on which a component depends.'''
    for item in dict_comps.items():
        key = item[0]
        comp = item[1]
        for hfile in comp.dep_our_hfiles:
            assert(hfile in dict_our_hfiles)
            hbase = fn_base(hfile)
            if(hbase in dict_comps):
                comp2 = dict_comps[hbase]
                if(comp2!=comp):
                    comp.dep_comps.add(comp2)
            else:
                #This our header doesn't belong to any component. We've ever warned it at make_components().
                pass
        for hfile in comp.dep_outside_hfiles:
            assert(hfile in dict_outside_hfiles)
            outside_pkg = dict_outside_hfiles[hfile]
            comp.dep_outside_pkgs.add(outside_pkg)


def output_ldep():
    for group_name in sorted(dict_pkgs.keys()):
        for pkg_name in sorted(dict_pkgs[group_name]):
            print '='*80
            print 'pakcage %s.%s dependency:'%(group_name,pkg_name)
            for comp in dict_pkgs[group_name][pkg_name]:
                message = '%s -> '%comp.name
                message += ', '.join(sorted(map(lambda x: x.name, comp.dep_comps)))
                message += '+(outside packages) ' + ','.join(sorted(map(lambda x: '.'.join(x), comp.dep_outside_pkgs)))
                print message

'''
create_graph_<range>_<level>
	<range> is one of [all, pkggrp, pkg]. It indicates those components included in the graph. 
	<level> is one of [comp, pkg, pkggrp]. It indicates what a node represents. 
Retrun Value:
	If <level> is "comp", return digraph.
        Else return (digraph, dict_edge2deps, dict_node2outsidepkgs).
        dict_edge2deps: edge -> list of component direct dependencies which been indicated by the edge.
        dict_node2outsidepkgs: node -> set of outside packages on which the node depends.
'''
def create_graph_all_comp():
    digraph = nx.DiGraph()
    for item in dict_comps.items():
        key = item[0]
        comp = item[1]
        digraph.add_node(comp)
        for comp2 in comp.dep_comps:
            digraph.add_edge(comp, comp2)
    return digraph

def create_graph_all_pkg():
    digraph = nx.DiGraph()
    dict_edge2deps = dict()
    dict_node2outsidepkgs = dict()
    for item in dict_comps.items():
        comp = item[1]
        pkg = '.'.join(comp.package)
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(pkg)
        if(pkg not in dict_node2outsidepkgs):
            dict_node2outsidepkgs[pkg] = set()
        dict_node2outsidepkgs[pkg].update(comp.dep_outside_pkgs)
        for comp2 in comp.dep_comps:
            pkg2 = '.'.join(comp2.package)
            if(pkg == pkg2):
                continue
            # Duplicated edges between two nodes will be stipped afterwards.
            digraph.add_edge(pkg, pkg2)
            key = (pkg,pkg2)
            if(key not in dict_edge2deps):
                dict_edge2deps[key] = list()
            dict_edge2deps[key].append((comp,comp2))
    return (digraph,dict_edge2deps,dict_node2outsidepkgs)

def create_graph_all_pkggrp():
    digraph = nx.DiGraph()
    dict_edge2deps = dict()
    dict_node2outsidepkgs = dict()
    for comp in dict_comps.values():
        group_name = comp.package[0]
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(group_name)
        if(group_name not in dict_node2outsidepkgs):
            dict_node2outsidepkgs[group_name] = set()
        dict_node2outsidepkgs[group_name].update(comp.dep_outside_pkgs)
        for comp2 in comp.dep_comps:
            group_name2 = comp2.package[0]
            if(group_name == group_name2):
                continue
            # Duplicated edges between two nodes will be stipped afterwards.
            digraph.add_edge(group_name, group_name2)
            key = (group_name,group_name2)
            if(key not in dict_edge2deps):
                dict_edge2deps[key] = list()
            dict_edge2deps[key].append((comp,comp2))
    return (digraph,dict_edge2deps,dict_node2outsidepkgs)

def create_graph_pkggrp_pkg(group_name):
    digraph = nx.DiGraph()
    dict_edge2deps = dict()
    dict_node2outsidepkgs = dict()
    for pkg_name in dict_pkgs[group_name]:
        # Adding a node does nothing if it is already in the graph.
        digraph.add_node(pkg_name)
        if(pkg_name not in dict_node2outsidepkgs):
            dict_node2outsidepkgs[pkg_name] = set()
        for comp in dict_pkgs[group_name][pkg_name]:
            dict_node2outsidepkgs[pkg_name].update(comp.dep_outside_pkgs)
            for comp2 in comp.dep_comps:
                (group_name2, pkg_name2) = comp2.package
                if(group_name!=group_name2 or pkg_name==pkg_name2):
                    continue
                assert(group_name==group_name2 and pkg_name!=pkg_name2)
                # Duplicated edges between two nodes will be stipped afterwards.
                digraph.add_edge(pkg_name, pkg_name2)
                key = (pkg_name, pkg_name2)
                if(key not in dict_edge2deps):
                    dict_edge2deps[key] = list()
                dict_edge2deps[key].append((comp,comp2))
    return (digraph,dict_edge2deps,dict_node2outsidepkgs)
    
def create_graph_pkg_comp(group_name, pkg_name):
    digraph = nx.DiGraph()
    package = (group_name, pkg_name)
    for comp in dict_pkgs[group_name][pkg_name]:
        digraph.add_node(comp)
        for comp2 in comp.dep_comps:
            package2 = comp2.package
            if(package2!=package):
                continue
            digraph.add_edge(comp, comp2)
    return digraph

def calculate_graph(digraph):
    size_graph = digraph.number_of_nodes()
    if(size_graph==0):
        return
    key_node = str
    key_edge = lambda x: str(x[0])+'->'+str(x[1])
    (cycles, dict_node2cycle) = make_DAG(digraph, key_node)
    (layers, dict_layer_no, redundant_edges) = layering_DAG(digraph, key_node)
    (ccd, dict_cd) = calc_ccd(digraph, cycles, layers)
    print '='*80
    print 'cycles detected(%d cycles): '%len(cycles)
    for min_node in sorted(cycles.keys(), key=str):
        cycle= cycles[min_node]
        message = '[cycle]%s nodes(%d nodes): '%(str(min_node),cycle.number_of_nodes())
        message += ' '.join(sorted(map(key_node, cycle.nodes())))
        print message
        message = '[cycle]%s edges(%d edges): '%(str(min_node),cycle.number_of_edges())
        message += ' '.join(sorted(map(key_edge, cycle.edges())))
        print message
    print '='*80
    print 'layers(%d layers):'%len(layers)
    def repr_node(node):
        cycle_key = dict_node2cycle[node]
        if(cycle_key):
            assert(node==cycle_key)
            str_node = '[cycle]' + str(node)
        else:
            str_node = str(node)
        return str_node
    for ind in range(0, len(layers)):
        print 'layer %d(%d nodes): '%(ind, len(layers[ind]))
        for node in layers[ind]:
            message = repr_node(node) + ' -> '
            message += ' '.join(sorted(map(repr_node, digraph.successors(node))))
            print message
#    print 'redundant edges stripped(%d edges): '%len(redundant_edges)
#    print ' '.join(sorted(map(key_edge, redundant_edges)))
    # CCD_fullBTree = (N+1)*log2(N+1)-N
    # ACD = CCD/N
    # NCCD = CCD/CCD_fullBTree
    acd = ccd*1.0/size_graph
    ccd_fullBTree = (size_graph+1)*(math.log(size_graph+1, 2)) - size_graph
    nccd = ccd/ccd_fullBTree
    print '='*80
    print 'SUMMARY:'
    print 'Nodes: %d\t Cycles: %d\t Layers: %d'%(size_graph, len(cycles), len(layers))
    print 'CCD: %d\t ACCD: %f\t NCCD: %f(typical range is [0.85, 1.10])'%(ccd, acd, nccd)
    

def test():
    cfile = '/home/zhichyu/work/probe/v6/atca/src/monApi/libMaAtm/src/MaAal2IntFrame.cc'
    hfiles = grep_hfiles(cfile)
    for elem in hfiles:
        print repr(elem)
    for elem in find_hfiles('/home/zhichyu/work/probe/v6/atca/src/monApi'):
        print repr(elem)
    for elem in find_cfiles('/home/zhichyu/work/probe/v6/atca/src/monApi'):
        print repr(elem)

if __name__ == '__main__':
    time_start = time.time()
    parse_conf()
    make_components()
    make_cdep()
    make_ldep()

    print '@'*80
    print 'analyzing dependencies among all components ...'
    digraph = create_graph_all_comp()
    calculate_graph(digraph)

    print '@'*80
    print 'analyzing dependencies among all packages ...'
    digraph,dict_edge2deps,dict_node2outsidepkgs = create_graph_all_pkg()
    print '='*80
    print 'dependencies on outside packages:'
    for item in dict_node2outsidepkgs.items():
        print str(item[0])+': '+' '.join(map(lambda x: '.'.join(x), list(item[1])))
    calculate_graph(digraph)

    print '@'*80
    print 'analyzing dependencies among all package groups ...'
    digraph,dict_edge2deps,dict_node2outsidepkgs = create_graph_all_pkggrp()
    print '='*80
    print 'dependencies on outside packages:'
    for item in dict_node2outsidepkgs.items():
        print str(item[0])+': '+' '.join(map(lambda x: '.'.join(x), list(item[1])))
    calculate_graph(digraph)

    for group_name in dict_pkgs:
        print '@'*80
        print 'analyzing dependencies among packages in the specified package group %s ...'%group_name
        digraph,dict_edge2deps,dict_node2outsidepkgs = create_graph_pkggrp_pkg(group_name)
        print '='*80
        print 'dependencies on outside packages:'
        for item in dict_node2outsidepkgs.items():
            print str(item[0])+': '+' '.join(map(lambda x: '.'.join(x), list(item[1])))
        calculate_graph(digraph)

    for group_name in dict_pkgs:
        for pkg_name in dict_pkgs[group_name]:
            print '@'*80
            print 'analyzing dependencies among components in the specified pakcage %s.%s ...'%(group_name, pkg_name)
            digraph = create_graph_pkg_comp(group_name, pkg_name)
            calculate_graph(digraph)

    time_end = time.time()
    print 'analyzing done in %s minutes.'%str((time_end-time_start)/60.0)
