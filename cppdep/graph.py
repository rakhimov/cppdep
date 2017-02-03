# Copyright (C) 2016-2017 Olzhas Rakhimov
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

from __future__ import absolute_import, division

import math

import networkx as nx
from networkx.drawing.nx_pydot import write_dot


class Graph(object):
    """Graph for dependency analysis among its nodes.

    Attributes:
        digraph: The underlying directed graph without self-loops.
    """

    def __init__(self, nodes, dep_filter=iter, is_external=lambda _: False):
        """Constructs a digraph for dependency analysis.

        Precondition:
            External nodes do not have successors in the graph.
            As a result, no cycles contain external nodes.
            All external nodes are at level 0.

        Args:
            nodes: Graph internal nodes with dependencies.
            dep_filter: A filter for node dependencies.
            is_external: Predicate to determine if a Graph node is external.
        """
        self.digraph = nx.DiGraph()
        self.cycles = {}  # {cyclic_graph: ([pre_edge], [suc_edge])}
        self.cycle2index = {}  # {cyclic_graph: cycle_index}
        self.node2cycle = {}  # {node: cyclic_graph}
        self.node2cd = {}  # {node: cd}
        self.node2level = {}  # {node: level}
        self.__dep_filter = dep_filter
        self.__is_external = is_external
        for node in nodes:
            assert not self.__is_external(node)
            self.digraph.add_node(node)
            for dependency in self.__dep_filter(node.dependencies()):
                assert node != dependency
                self.digraph.add_edge(node, dependency)

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
        subgraphs = nx.strongly_connected_component_subgraphs(self.digraph,
                                                              copy=False)
        for subgraph in list(subgraphs):
            if subgraph.number_of_nodes() == 1:
                continue  # not a cycle
            pre_edges = []
            suc_edges = []
            for node in subgraph:
                assert node not in self.node2cycle
                assert node in self.digraph  # no accidental copying
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

        cycle_order = lambda x: min(str(u) for u in x)
        for index, cycle in enumerate(sorted(self.cycles, key=cycle_order)):
            self.cycle2index[cycle] = index

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
            """Returns CD contribution of a node."""
            if self.__is_external(node):
                return 0
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
                level = (not self.__is_external(node) if node not in self.cycles
                         else node.number_of_nodes())
                if self.digraph[node]:
                    level += max(_get_level(x) for x in self.digraph[node])
                self.node2level[node] = level
            return self.node2level[node]
        for node in self.digraph:
            _get_level(node)

    def get_level(self, node):
        """Returns the level of the component node."""
        if node in self.node2cycle:
            return self.node2level[self.node2cycle[node]]
        return self.node2level[node]

    def print_cycles(self, printer):
        """Prints cycles only after reduction."""
        if not self.cycles:
            return
        printer('=' * 80)
        printer('%d cycles detected:\n' % len(self.cycles))
        for cycle, i in sorted(self.cycle2index.items(), key=lambda x: x[1]):
            printer('cycle #%d (%d nodes):' % (i, cycle.number_of_nodes()),
                    ', '.join(sorted(str(x) for x in cycle.nodes())))
            printer('cycle #%d (%d edges):' % (i, cycle.number_of_edges()),
                    ' '.join(sorted(str(edge[0]) + '->' + str(edge[1])
                                    for edge in cycle.edges())))
            printer()

    def print_levels(self, printer, reduced_dependencies=None):
        """Prints levels of nodes.

        Args:
            printer: The printer object.
            reduced_dependencies: Print node dependencies in reduced form.
                If None, no dependencies are printed at all.
        """
        printer('=' * 80)
        max_level = max(self.node2level.values())
        printer('%d level(s):\n' % max_level)

        def _stabilize(node):
            """Returns string for report stabilization sort."""
            if node in self.cycles:
                return min(str(x) for x in node)
            return str(node)

        def _print_dependencies(node):
            """Prints dependencies of the levelized components."""
            if reduced_dependencies is None or self.__is_external(node):
                return
            for v in sorted(self.digraph[node] if reduced_dependencies
                            else set(self.__dep_filter(node.dependencies())),
                            key=lambda x: (self.get_level(x), str(x))):
                if v in self.node2cycle:
                    cycle = self.node2cycle[v]
                    printer('\t\t%d. %s <%d>' % (self.node2level[cycle], str(v),
                                                 self.cycle2index[cycle]))
                else:
                    printer('\t\t%d. %s' % (self.node2level[v], str(v)))

        level_num = -1
        for node, level in sorted(self.node2level.items(),
                                  key=lambda x: (x[1], _stabilize(x[0]))):
            while level > level_num:
                level_num += 1
                printer('level %d:' % level_num)
            if node in self.cycles:
                cycle_index = self.cycle2index[node]
                for v in sorted(node, key=str):
                    printer('\t%s <%d>' % (str(v), cycle_index))
                    _print_dependencies(v)
            else:
                printer('\t' + str(node))
                _print_dependencies(node)

    def print_summary(self, printer):
        """Calculates and prints overall CCD metrics."""
        ccd = 0
        for node, cd in self.node2cd.items():
            if node in self.cycles:
                ccd += node.number_of_nodes() * cd
            else:
                ccd += cd
        num_nodes = len([x for x in self.digraph if not self.__is_external(x)])
        average_cd = ccd / num_nodes
        # CCD_Balanced_BTree = (N + 1) * log2(N + 1) - N
        ccd_btree = (num_nodes + 1) * math.log(num_nodes + 1, 2) - num_nodes
        normalized_ccd = ccd / ccd_btree
        printer('=' * 80)
        printer('SUMMARY:')
        printer('Components: %d\t Cycles: %d\t Levels: %d' %
                (num_nodes, len(self.cycles), max(self.node2level.values())))
        typical_range = '[0.85, 1.10]'
        printer('CCD: %d\t ACCD: %.2f\t NCCD: %.2f (typical range is %s)' %
                (ccd, average_cd, normalized_ccd, typical_range))

    def write_dot(self, file_basename):
        """Writes graph into a file in Graphviz DOT format.

        Args:
            file_basename: The output file name without extension.
        """
        write_dot(self.digraph, file_basename + '.dot')
