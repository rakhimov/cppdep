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

    Args:
        digraph: The DAG(Directed Acyclic Graph).
        key_node: An optional sorting key (str).

    Returns:
        List of layers
    """
    out_degrees = digraph.out_degree()
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

    for i in range(1, len(layers)):
        for node in layers[i]:
            for suc_node in digraph.successors(node):
                # Edges between adjacent layers are always non-redundant
                # if the graph is a DAG(ie. no cycles).
                if layer_no[suc_node] == i - 1:
                    continue
                digraph.remove_edge(node, suc_node)
                if not is_reachable(digraph, node, suc_node):
                    digraph.add_edge(node, suc_node)

    return layers


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


class Graph(object):
    """Graph for dependency analysis among its nodes."""

    def __init__(self, nodes, node_name_generator):
        self.digraph = nx.DiGraph()
        self.cycles = {}  # {cyclic_graph: ([pre_edge], [suc_edge])}
        self.node2cycle = {}  # {node: cyclic_graph}
        for node in nodes:
            node_name = node_name_generator(node)
            # Adding a node does nothing if it is already in the graph.
            self.digraph.add_node(node_name)
            for dependency in node.dependencies():
                dependency_name = node_name_generator(dependency)
                if node_name == dependency_name:
                    continue
                # Duplicated edges between two nodes
                # will be stripped afterwards.
                self.digraph.add_edge(node_name, dependency_name)

    # pylint: disable=invalid-name
    def __transitive_reduction(self):
        """Transitive reduction for acyclic graphs."""
        assert nx.is_directed_acyclic_graph(self.digraph)
        for u in self.digraph:
            transitive_vertex = []
            for v in self.digraph[u]:
                transitive_vertex.extend(x for _, x in
                                         nx.dfs_edges(self.digraph, v))
            self.digraph.remove_edges_from((u, x) for x in transitive_vertex)

    def __condensation(self):
        """Produces condensation of cyclic graphs."""
        subgraphs = nx.strongly_connected_component_subgraphs(self.digraph)
        for subgraph in list(subgraphs):
            if subgraph.number_of_nodes() == 1:
                continue  # not a cycle
            pre_edges = []
            suc_edges = []
            for node in subgraph:
                assert node not in self.node2cycle
                self.node2cycle[node] = subgraph
                for pre_node in self.digraph.predecessors(node):
                    if not subgraph.has_node(pre_node):
                        pre_edges.append((pre_node, node))
                        self.digraph.add_edge(pre_node, subgraph)
                for suc_node in self.digraph.successors(node):
                    if not subgraph.has_node(suc_node):
                        suc_edges.append((node, suc_node))
                        self.digraph.add_edge(subgraph, suc_node)
                self.digraph.remove_node(node)
            assert subgraph not in self.cycles
            self.cycles[subgraph] = (pre_edges, suc_edges)

    # pylint: disable=invalid-name
    def __decondensation(self):
        """Reverts the effect of the condensation."""
        for subgraph, (pre_edges, suc_edges) in self.cycles.items():
            assert self.digraph.has_node(subgraph)
            for u, v in pre_edges:
                if (self.digraph.has_edge(u, subgraph) or
                        (u in self.node2cycle and
                         self.digraph.has_edge(self.node2cycle[u], subgraph))):
                    self.digraph.add_edge(u, v)
            for u, v in suc_edges:
                if (self.digraph.has_edge(subgraph, v) or
                        (v in self.node2cycle and
                         self.digraph.has_edge(subgraph, self.node2cycle[v]))):
                    self.digraph.add_edge(u, v)
            self.digraph.add_nodes_from(subgraph)
            self.digraph.add_edges_from(subgraph.edges())
            self.digraph.remove_node(subgraph)

    def reduce(self):
        """Applies transitive reduction to the graph.

        If the graph contains cycles,
        the graph is minimized instead.
        """
        assert self.digraph.number_of_selfloops() == 0
        self.__condensation()
        self.__transitive_reduction()
        self.__decondensation()

    def print_cycles(self):
        """Prints cycles only after reduction."""
        if not self.cycles:
            return
        print('=' * 80)
        print('%d cycles detected:\n' % len(self.cycles))
        for i, cycle in enumerate(self.cycles):
            print('cycle #%d (%d nodes):' % (i, cycle.number_of_nodes()),
                  ', '.join(sorted(str(x) for x in cycle.nodes())))
            print('cycle #%d (%d edges):' % (i, cycle.number_of_edges()),
                  ' '.join(sorted(str(edge[0]) + '->' + str(edge[1])
                                  for edge in cycle.edges())))
            print()

    def write_dot(self, file_basename):
        """Writes graph into a file in Graphviz DOT format.

        Args:
            file_basename: The output file name without extension.
        """
        write_dot(self.digraph, file_basename + '.dot')


def create_graph_all_pkggrp(components):
    return Graph(components.values(), lambda x: x.package.group.name)


def create_graph_pkggrp_pkg(group_packages):
    return Graph(group_packages.values(), lambda x: x.name)


def create_graph_pkg_component(pkg_components):
    package_graph = Graph([], None)
    digraph = package_graph.digraph
    for component in pkg_components:
        digraph.add_node(str(component))
        for dep_component in component.dep_components:
            if dep_component.package == component.package:
                digraph.add_edge(str(component), str(dep_component))
    return package_graph


def _print_layers(layers, node2cycle, digraph):
    print('=' * 80)
    print('layers (%d layer(s)):\n' % len(layers))

    def repr_node(node):
        cycle_key = node2cycle[node]
        if cycle_key:
            assert node == cycle_key
            str_node = '[cycle]' + str(node)
        else:
            str_node = str(node)
        return str_node

    for i, layer in enumerate(layers):
        print('layer %d (%d node(s)):\n' % (i, len(layer)))
        for node in layer:
            name = repr_node(node)
            print('\t' + name)
            for dep_name in sorted(repr_node(x) for x in
                                   digraph.successors(node)):
                print('\t' + ' ' * len(name) + '\t%s' % dep_name)
            print()


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


def calculate_graph(digraph):
    assert digraph.number_of_nodes()
    size_graph = digraph.number_of_nodes()
    # TODO: Side effect on graph size?!
    cycles, node2cycle = make_dag(digraph, str)
    layers = layering_dag(digraph, str)

    _print_layers(layers, node2cycle, digraph)
    _print_ccd(digraph, cycles, layers, size_graph)
