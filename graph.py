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


class Graph(object):
    """Graph for dependency analysis among its nodes.

    Attributes:
        digraph: The underlying directed graph without self-loops.
    """

    def __init__(self, nodes):
        """Constructs a digraph for dependency analysis.

        Args:
            nodes: Graph nodes with dependencies.
        """
        self.digraph = nx.DiGraph()
        self.cycles = {}  # {cyclic_graph: ([pre_edge], [suc_edge])}
        self.node2cycle = {}  # {node: cyclic_graph}
        self.node2cd = {}  # {node: cd}
        self.node2level = {}  # {node: level}
        for node in nodes:
            self.digraph.add_node(str(node))
            for dependency in node.dependencies():
                assert node != dependency
                self.digraph.add_edge(str(node), str(dependency))

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

    def analyze(self):
        """Applies transitive reduction to the graph and calculates metrics.

        If the graph contains cycles,
        the graph is minimized instead.
        """
        assert self.digraph.number_of_selfloops() == 0
        self.__condensation()
        self.__transitive_reduction()
        self.__calculate_ccd()
        self.__calculate_levels()
        self.__decondensation()

    def __calculate_ccd(self):
        """Calculates CCD for nodes.

        The graph must be minimized with condensed cycles.
        """
        descendants = {}  # {node: set(descendant_node)} for memoization.

        def _get_descendants(node):
            """Returns a set of descendants of a node."""
            if node not in descendants:
                node_descendants = set()
                for v in self.digraph[node]:
                    node_descendants.add(v)
                    node_descendants.update(_get_descendants(v))
                descendants[node] = node_descendants
            return descendants[node]

        def _get_cd(node):
            """Retruns CD contribution of a node."""
            return 1 if node not in self.cycles else node.number_of_nodes()

        for node in self.digraph:
            cd = _get_cd(node)
            for descendant in _get_descendants(node):
                cd += _get_cd(descendant)
            self.node2cd[node] = cd

    def __calculate_levels(self):
        """Calculates levels for nodes."""
        def _get_level(node):
            if node not in self.node2level:
                level = 1 if node not in self.cycles else node.number_of_nodes()
                if self.digraph[node]:
                    level += max(_get_level(x) for x in self.digraph[node])
                self.node2level[node] = level
            return self.node2level[node]
        for node in self.digraph:
            _get_level(node)

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

    def print_levels(self):
        """Prints levels of nodes."""
        print('=' * 80)
        max_level = max(self.node2level.values())
        print('%d level(s):\n' % max_level)
        level_num = 0
        cycle_num = 0
        for node, level in sorted(self.node2level.items(), key=lambda x: x[1]):
            while level > level_num:
                level_num += 1
                print('level %d:' % level_num)
            if node in self.cycles:
                for v in node:
                    print('\t%s <%d>' % (str(v), cycle_num))
                cycle_num += 1
            else:
                print('\t' + str(node))

    def print_summary(self):
        """Calculates and prints overall CCD metrics."""
        ccd = 0
        for node, cd in self.node2cd.items():
            if node in self.cycles:
                ccd += node.number_of_nodes() * cd
            else:
                ccd += cd
        num_nodes = self.digraph.number_of_nodes()
        average_cd = ccd / num_nodes
        # CCD_Balanced_BTree = (N + 1) * log2(N + 1) - N
        ccd_btree = (num_nodes + 1) * math.log(num_nodes + 1, 2) - num_nodes
        normalized_ccd = ccd / ccd_btree
        print('=' * 80)
        print('SUMMARY:')
        print('Nodes: %d\t Cycles: %d\t Levels: %d' %
              (num_nodes, len(self.cycles), max(self.node2level.values())))
        print('CCD: %d\t ACCD: %f\t NCCD: %f(typical range is [0.85, 1.10])' %
              (ccd, average_cd, normalized_ccd))

    def write_dot(self, file_basename):
        """Writes graph into a file in Graphviz DOT format.

        Args:
            file_basename: The output file name without extension.
        """
        write_dot(self.digraph, file_basename + '.dot')
