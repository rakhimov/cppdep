#!/usr/bin/env python

import sys
import os.path
import re
import hashlib
import math
import time
# ElementTree is introduced in by Python 2.5.
from xml.etree import ElementTree

'''
A Python Graph API? http://wiki.python.org/moin/PythonGraphApi
It seems that the best one is NetworkX(http://networkx.lanl.gov/).
'''

import networkx as nx
from graph_algorithm import *

def md5sum(fpath):
    m = hashlib.md5()
    f = open(fpath, 'rb')
    m.update(f.read())
    f.close()
    return m.digest()

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

def fn_base(path):
    return os.path.splitext(os.path.basename(path))[0]

def find_hfiles(path):
    hfiles = dict()
    file_name = '(?i).*\.h(xx|\+\+|h|pp|)$'
    for elem in find(path, file_name):
        basename = fn_base(elem[0])
        hpath = elem[1]
        hfiles[basename] = hpath
    return hfiles

def find_cfiles(path):
    cfiles = dict()
    file_name = '(?i).*\.c(xx|\+\+|c|pp|)$'
    for elem in find(path, file_name):
        basename = fn_base(elem[0])
        cpath = elem[1]
        cfiles[basename] = cpath
    return cfiles

class component(object):
    def __init__(self, name, hpath, cpath):
        self.package = ('anonymous', 'anonymous')
        self.name = name
        self.hpath = hpath
        self.cpath = cpath
        self.dep_hfiles = list()
        self.dep_comps = list()
        self.dep_outside_pkgs = set()
    def __str__(self):
        return self.name

# Following two global variables are initialized by parse_conf().
dict_outside_conf = dict()
dict_our_conf = dict()

dict_outside_hfiles = dict()
dict_our_hfiles = dict()
dict_pkgs  = dict()
dict_comps = dict()

def parse_conf():
    global dict_outside_conf
    global dict_our_conf
    root = ElementTree.parse('dep_conf.xml').getroot()
    for pkg_group in root.findall('outside_package_group'):
        group_name = pkg_group.get('name')
        dict_outside_conf[group_name] = dict()
        for pkg in pkg_group.findall('package'):
            pkg_name = pkg.get('name')
            inc_paths = pkg.text.strip().split()
            dict_outside_conf[group_name][pkg_name] = inc_paths
    for pkg_group in root.findall('our_package_group'):
        group_name = pkg_group.get('name')
        group_path = pkg_group.get('path')
        dict_our_conf[group_name] = dict()
        for pkg_path in pkg_group.text.strip().split():
            pkg_path = os.path.normpath(os.path.join(group_path, pkg_path))
            pkg_name = os.path.basename(pkg_path)
            dict_our_conf[group_name][pkg_name] = pkg_path

def make_components():
    '''pair hfiles and cfiles.'''
    global dict_outside_hfiles
    global dict_our_hfiles
    global dict_pkgs
    global dict_comps
    for group_name in dict_outside_conf:
        for pkg_name in dict_outside_conf[group_name]:
            pkg = (group_name, pkg_name)
            for inc_path in dict_outside_conf[group_name][pkg_name]:
                hfiles = find_hfiles(inc_path)
                for item in hfiles.items():
                    dict_outside_hfiles[item[0]] = pkg
    for group_name in dict_our_conf:
        dict_pkgs[group_name] = dict()
        for pkg_name in dict_our_conf[group_name]:
            pkg_path = dict_our_conf[group_name][pkg_name]
            dict_pkgs[group_name][pkg_name] = list()
            hfiles = find_hfiles(pkg_path)
            cfiles = find_cfiles(pkg_path)
            for key in hfiles.keys():
                if(key in dict_our_hfiles):
                    digest1 = md5sum(dict_our_hfiles[key])
                    digest2 = md5sum(hfiles[key])
                    if(digest1==digest2):
                        same_diff = 'same'
                    else:
                        same_diff = 'different'
                    print 'warning: following headers have the same basename(%s content): %s, %s'%(same_diff, dict_our_hfiles[key], hfiles[key])
            dict_our_hfiles.update(hfiles)
            keys = list(cfiles.keys())
            for key in keys:
                if(key in hfiles):
                    comp = component(key, hfiles[key], cfiles[key])
                    dict_pkgs[group_name][pkg_name].append(comp)
                    comp.package = (group_name, pkg_name)
                    dict_comps[key] = comp
                    del hfiles[key]
                    del cfiles[key]
            if(len(hfiles) or len(cfiles)):
                message = 'warning: failed to put follow files into any components (in package %s.%s): '%(group_name, pkg_name)
                if(len(hfiles)):
                    message += ', '.join(map(os.path.basename, hfiles.values()))
                if(len(cfiles)):
                    message += ', '.join(map(os.path.basename, cfiles.values()))
                print message

def make_cdep():
    '''determine all hfiles on which a cfile depends.
    Note: Recursively parsing does not work since there may be a cycle dependency among headers.'''
    set_bad_hfiles = set()
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
        ind = 0
        while(1):
            if(ind>=len(hfiles)):
                break
            hfile = hfiles[ind]
            hfile_base = fn_base(hfile)
            hpath = None
            if(hfile_base in dict_our_hfiles):
                hpath = dict_our_hfiles[hfile_base]
                hfiles2 = grep_hfiles(hpath)
                for hfile2 in hfiles2:
                    if(hfile2 not in hfiles):
                        hfiles.append(hfile2)
                ind += 1
            elif(hfile_base in dict_outside_hfiles):
                # Dependencies on outside packages will be checked at make_ldep().
                ind += 1
            else:
                set_bad_hfiles.add(hfile)
                del hfiles[ind]
        comp.dep_hfiles = hfiles
    if(len(set_bad_hfiles)!=0):
        print 'warning: failed to locate following headers when analyzing compilation dependencies: ', ' '.join(set_bad_hfiles)

def make_ldep():
    '''determine all components on which a component depends.'''
    for item in dict_comps.items():
        key = item[0]
        comp = item[1]
        for hfile in comp.dep_hfiles:
            hfile_base = fn_base(hfile)
            if(hfile_base in dict_our_hfiles):
                if(hfile_base in dict_comps):
                    comp2 = dict_comps[hfile_base]
                    if((comp2.name!=comp.name) and (comp2 not in comp.dep_comps)):
                        comp.dep_comps.append(comp2)
                else:
                    #This our header doesn't belong to any component. We've ever warned it at make_components().
                    pass
            elif(hfile_base in dict_outside_hfiles):
                outside_pkg = dict_outside_hfiles[hfile_base]
                comp.dep_outside_pkgs.add(outside_pkg)
            else:
                # We've removed and warned all bad(failed to locate) hfiles at make_cdep().
                assert(0)

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
    strip_redundant_edges(digraph, key_edge)
    #print '='*80
    #print 'edges after strip_redundant_edges()(%d):'%digraph.number_of_edges()
    #print ' '.join(sorted(map(lambda x: str(x[0])+'->'+str(x[1]), digraph.edges())))
    (cycles, dict_node2cycle) = strip_cycles(digraph, key_node)
    (layers, dict_layer_no) = layering(digraph, key_node)
    (ccd, dict_cd) = calc_ccd(digraph, cycles, layers)
    print '='*80
    print 'cycles: '
    for min_node in sorted(cycles.keys(), key=str):
        cycle= cycles[min_node]
        message = 'nodes of cycle %s(%d): '%(str(min_node),cycle.number_of_nodes())
        message += ' '.join(sorted(map(key_node, cycle.nodes())))
        print message
        message = 'edges of cycle %s(%d): '%(str(min_node),cycle.number_of_edges())
        message += ' '.join(sorted(map(key_edge, cycle.edges())))
        print message
    print '='*80
    print 'layers:'
    for ind in range(0, len(layers)):
        message = 'layer %d: '%(ind)
        layer_msgs = list()
        for node in layers[ind]:
            cycle_key = dict_node2cycle[node]
            if(cycle_key):
                assert(node==cycle_key)
                str_node = '[cycle]' + str(node)
            else:
                str_node = str(node)
            layer_msgs.append(str_node)
        message += ' '.join(sorted(layer_msgs))
        print message
    # CCD_fullBTree = (N+1)*log2(N+1)-N
    # ACD = CCD/N
    # NCCD = CCD/CCD_fullBTree
    acd = ccd*1.0/size_graph
    ccd_fullBTree = (size_graph+1)*(math.log(size_graph+1, 2)) - size_graph
    nccd = ccd/ccd_fullBTree
    print '='*80
    print 'SUMMARY:'
    print 'Nodes: %d\t Layers: %d'%(size_graph, len(layers))
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
