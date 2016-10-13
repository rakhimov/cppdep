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

"""Graph algorithms used in Large-Scale C++ Software Design (ch. 4, appendix C).

A Python Graph API? http://wiki.python.org/moin/PythonGraphApi
It seems that the best one is NetworkX(http://networkx.lanl.gov/).
"""

from __future__ import print_function, absolute_import, division

import math
import sys

import networkx as nx
from networkx.drawing.nx_pydot import write_dot


def is_reachable(digraph, node_parent, node_target):
    """Determines if a node is a descendant of another.

    Args:
        digraph: The host graph.
        node_parent: The node to start the reachability search.
        node_target: The target node under reachability question.

    Returns:
        True if node_target is reachable from node_parent.
        False if the node parent is the node target.
    """
    if node_parent == node_target:
        return False
    reachable_nodes = set([node_parent])
    current_nodes = set([node_parent])
    while current_nodes:
        next_nodes = set()
        for node in current_nodes:
            next_nodes.update(digraph.successors(node))
        if node_target in next_nodes:
            return True
        next_nodes.difference_update(reachable_nodes)
        reachable_nodes.update(next_nodes)
        current_nodes = next_nodes

    return False


def make_dag(digraph, key_node=None):
    """Makes out a DAG.

    Only one node in each cycle is kept in the original graph.
    That node is used as the key of cycle subgraphs.
    (key_node != None) indicates selecting the minimal one
    among all nodes of the cycle per key_node.
    Otherwise which one being selected is an implementation specific behavior.
    Note: Selfloop edges will be stripped silently.
    """
    # output_graph(digraph)
    cycles = {}
    node2cycle = {}
    for node in digraph.nodes_iter():
        node2cycle[node] = None
    # Strip all selfloop edges silently.
    digraph.remove_edges_from(digraph.selfloop_edges())
    for subgraph in nx.strongly_connected_component_subgraphs(digraph):
        if subgraph.number_of_nodes() == 1:
            # Selfloop edges have been stripped.
            assert not subgraph.number_of_edges()
            continue
        nodes = subgraph.nodes()
        if key_node:
            min_node = min(nodes, key=key_node)
        else:
            min_node = nodes[0]
        cycles[min_node] = subgraph
        for node in nodes:
            node2cycle[node] = min_node

    for min_node in cycles:
        nodes = cycles[min_node].nodes()
        nodes.remove(min_node)
        # print('min_node: %s, other nodes: ' % str(min_node), ')
        # '.join(map(str, nodes))
        for node in nodes:
            pre_nodes = digraph.predecessors(node)
            suc_nodes = digraph.successors(node)
            for pre_node in pre_nodes:
                if (pre_node == min_node or
                        (pre_node in nodes) or
                        digraph.has_edge(pre_node, min_node)):
                    continue
                digraph.add_edge(pre_node, min_node)
            for suc_node in suc_nodes:
                if (suc_node == min_node or
                        (suc_node in nodes) or
                        digraph.has_edge(min_node, suc_node)):
                    continue
                digraph.add_edge(min_node, suc_node)
            # All edges assiciated with a node will also be removed when
            # removing the node from the graph.
            digraph.remove_node(node)
    return cycles, node2cycle


def layering_dag(digraph, key_node=None):
    """Layering all nodes and strip redundant edges in the graph.

    Assumption: digraph is a DAG(Directed Acyclic Graph).

    Returns:
        (List of layers, nodes-to-layer dictionary, list of redundant edges)
    """
    out_degrees = digraph.out_degree()
    # print(digraph.out_degree())
    nodes_layer = [k for k, v in out_degrees.items() if v == 0]
    assert nodes_layer or not list(digraph.nodes())

    layer_no = {}
    layers = []
    cur_layer_no = 0
    while nodes_layer:
        layer_no.update({node: cur_layer_no for node in nodes_layer})
        if key_node:
            nodes_layer.sort(key=key_node)
        layers.append(nodes_layer)

        nodes_layer_next = set()
        for node in nodes_layer:
            for predecessor in digraph.predecessors(node):
                out_degrees[predecessor] -= 1
                nodes_layer_next.add(predecessor)

        nodes_layer = [node for node in nodes_layer_next
                       if out_degrees[node] <= 0]
        cur_layer_no += 1

    redundant_edges = []
    for i in range(1, len(layers)):
        for node in layers[i]:
            for suc_node in digraph.successors(node):
                # Edges between adjacent layers are always non-redundant
                # if the graph is a DAG(ie. no cycles).
                if layer_no[suc_node] == i - 1:
                    continue
                digraph.remove_edge(node, suc_node)
                if is_reachable(digraph, node, suc_node):
                    redundant_edges.append((node, suc_node))
                    continue
                digraph.add_edge(node, suc_node)

    return layers, layer_no, redundant_edges


def calc_ccd(digraph, cycles, layers):
    """Calculates CCD.

    Args:
        digraph: A general graph of components, or packages, or groups.
        cycles: Cycles in the graph.
        layers: Layered nodes.

    Returns:
        (CCD value, {node: ccd})
    """
    assert digraph.nodes()
    node2cd = {}
    for node in digraph.nodes():
        node2cd[node] = 1
    min_nodes = set(cycles.keys())
    for layer in layers:
        for node in layer:
            for suc_node in digraph.successors(node):
                node2cd[node] += node2cd[suc_node]
            if node in min_nodes:
                node2cd[node] += len(cycles[node]) - 1
    for min_node in cycles:
        min_node_cd = node2cd[min_node]
        for node in cycles[min_node].nodes_iter():
            if node != min_node:
                node2cd[node] = min_node_cd
    return sum(node2cd.values()), node2cd


def output_graph(digraph, destination=sys.stdout):
    print('nodes(%d): ' % digraph.number_of_nodes(),
          ' '.join(map(str, digraph.nodes())), file=destination)
    print('edges(%d): ' % digraph.number_of_edges(),
          ' '.join(str(x[0]) + '->' + str(x[1]) for x in digraph.edges()),
          file=destination)


class Graph(object):
    """Graph for dependency analysis among its nodes.

    create_graph_<range>_<level>
            <range> is one of [all, pkggrp, pkg].
            It indicates those components included in the graph.

            <level> is one of [component, pkg, pkggrp].
            It indicates what a node represents.

    Return Value:
            If <level> is "component", return digraph.
            Else return (digraph, edge2deps, node2externalpkgs).
            edge2deps: edge -> list of component direct dependencies
                which been indicated by the edge.
            node2externalpkgs: node -> set of external packages
                on which the node depends.
    """

    def __init__(self, nodes, node_name_generator, gather_metrics=True):
        self.digraph = nx.DiGraph()
        self.__edge2deps = {}
        self.__external_graphs = {}
        for node in nodes:
            node_name = node_name_generator(node)
            # Adding a node does nothing if it is already in the graph.
            self.digraph.add_node(node_name)
            for dependency in node.dependencies():
                dependency_name = node_name_generator(dependency)
                if node_name == dependency_name:
                    continue
                # Duplicated edges between two nodes will be stripped afterwards.
                self.digraph.add_edge(node_name, dependency_name)

        if gather_metrics:
            self.gather_dependency_metrics(nodes, node_name_generator)

    def gather_dependency_metrics(self, nodes, node_name_generator):
        for node in nodes:
            node_name = node_name_generator(node)
            if node_name not in self.__external_graphs:
                self.__external_graphs[node_name] = set()
            self.__external_graphs[node_name].update(node.external_graphs())
            for dependency in node.dependencies():
                dependency_name = node_name_generator(dependency)
                if node_name == dependency_name:
                    continue
                key = (node_name, dependency_name)
                if key not in self.__edge2deps:
                    self.__edge2deps[key] = []
                self.__edge2deps[key].append((node, dependency))

    def print_info(self):
        print('=' * 80)
        print('each edge in the original graph logically consists of '
              'some cross-component dependencies:')
        for edge, nodes in self.__edge2deps.items():
            message = '->'.join(edge) + ': '
            num_deps = 5 if len(nodes) > 5 else len(nodes)
            message += ' '.join('->'.join(x) for x in nodes[0:num_deps])
            if num_deps < len(nodes):
                message += ' ...'
            print(message)
        print('=' * 80)
        print('each node in the original graph depends on some external packages:')
        for node_name, graphs in self.__external_graphs.items():
            print(node_name + ': ' + ' '.join('.'.join(x) for x in graphs))


def create_graph_all_component(components):
    return Graph(components.values(), str, False)


def create_graph_all_pkg(components):
    return Graph(components.values(),
                 lambda x: x.package.group.name + '.' + x.package.name)


def create_graph_all_pkggrp(components):
    return Graph(components.values(), lambda x: x.package.group.name)


def create_graph_pkggrp_pkg(group_packages):
    return Graph(group_packages.values(), lambda x: x.name)


def create_graph_pkg_component(pkg_components):
    digraph = nx.DiGraph()
    for component in pkg_components:
        digraph.add_node(str(component))
        for dep_component in component.dep_components:
            if (dep_component.package.group == component.package.group and
                    dep_component.package == component.package):
                digraph.add_edge(str(component), str(dep_component))
    return digraph


def _print_cycles(cycles, key_node, key_edge):
    if not cycles:
        return
    print('=' * 80)
    print('cycles detected(%d cycles): ' % len(cycles))
    for min_node in sorted(cycles.keys(), key=str):
        cycle = cycles[min_node]
        message = '[cycle]%s nodes(%d nodes): ' % (
            str(min_node), cycle.number_of_nodes())
        message += ' '.join(sorted(key_node(x) for x in cycle.nodes()))
        print(message)
        message = '[cycle]%s edges(%d edges): ' % (
            str(min_node), cycle.number_of_edges())
        message += ' '.join(sorted(key_edge(x) for x in cycle.edges()))
        print(message)


def _print_layers(layers, node2cycle, digraph):
    print('=' * 80)
    print('layers(%d layers):' % len(layers))

    def repr_node(node):
        cycle_key = node2cycle[node]
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
            message += ' '.join(sorted(repr_node(x) for x in
                                       digraph.successors(node)))
            print(message)


def _print_redundant_edges(redundant_edges, key_edge):
    print('redundant edges stripped(%d edges): ' % len(redundant_edges))
    print(' '.join(sorted(key_edge(x) for x in redundant_edges)))


def _print_ccd(digraph, cycles, layers, size_graph):
    ccd, _ = calc_ccd(digraph, cycles, layers)
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


def _dot_cycles(digraph, cycles, dot_basename):
    if cycles and dot_basename:
        if cycles:
            cycle_graph = nx.DiGraph()
            for cycle in cycles.values():
                cycle_graph.add_edges_from(cycle.edges_iter())
            write_dot(cycle_graph, dot_basename + '_cycles.dot')
        write_dot(digraph, dot_basename + '_final.dot')


def calculate_graph(digraph, dot_basename=None):
    size_graph = digraph.number_of_nodes()
    if size_graph == 0:
        return
    if dot_basename:
        write_dot(digraph, dot_basename + '_orig.dot')

    key_node = str
    def key_edge(edge):
        return str(edge[0]) + '->' + str(edge[1])

    # TODO: Side effect on graph size?!
    cycles, node2cycle = make_dag(digraph, key_node)
    layers, _, redundant_edges = layering_dag(digraph, key_node)

    _print_cycles(cycles, key_node, key_edge)
    _print_layers(layers, node2cycle, digraph)
    _print_redundant_edges(redundant_edges, key_edge)
    _print_ccd(digraph, cycles, layers, size_graph)
    _dot_cycles(digraph, cycles, dot_basename)
