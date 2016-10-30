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

"""Tests for graph extension functions."""

from __future__ import print_function, division, absolute_import

import math
from tempfile import NamedTemporaryFile

import networkx as nx
from nose.tools import assert_equal

from graph import make_dag, layering_dag, calc_ccd


_REPORT = "./test/graph_report.txt"


def output_graph(digraph, destination):
    """Prints the graph nodes and edges."""
    print('nodes(%d): ' % digraph.number_of_nodes(),
          ' '.join(map(str, digraph.nodes())), file=destination)
    print('edges(%d): ' % digraph.number_of_edges(),
          ' '.join(str(x[0]) + '->' + str(x[1]) for x in digraph.edges()),
          file=destination)


def generate_graph(destination):
    """Prints the graph and metrics into the specified destination."""
    digraph = nx.DiGraph()
    edges1 = [(1, 1), (1, 2), (2, 4), (2, 6), (6, 2), (6, 7), (7, 6)]
    edges2 = [(1, 3), (1, 5), (3, 4), (3, 5), (3, 8), (8, 9), (9, 3)]
    edges3 = [(10, 11), (10, 12), (11, 12), (12, 11)]
    digraph.add_edges_from(edges1)
    digraph.add_edges_from(edges2)
    digraph.add_edges_from(edges3)
    print('=' * 80, file=destination)
    print('original digraph: ', file=destination)
    output_graph(digraph, destination)
    cycles, _ = make_dag(digraph)
    print('=' * 80, file=destination)
    print('after stripping cycles: ', file=destination)
    output_graph(digraph, destination)
    for (min_node, cycle) in cycles.items():
        print('cycle %s: ' % str(min_node), file=destination)
        output_graph(cycle, destination)
    layers = layering_dag(digraph)
    print('=' * 80, file=destination)
    print('after layering: ', file=destination)
    output_graph(digraph, destination)
    for i, layer in enumerate(layers):
        print('layer %d: ' % i + str(layer), file=destination)

    (ccd, node2cd) = calc_ccd(digraph, cycles, layers)
    print('=' * 80, file=destination)
    size = len(node2cd)
    ccd_full_btree = (size + 1) * (math.log(size + 1, 2)) - size
    nccd = ccd / ccd_full_btree
    print('CCD: %d\t NCCD: %f(typical range is [0.85, 1.10])\t SIZE: %d' %
          (ccd, nccd, size), file=destination)
    print('cumulate dependencies: ' + str(node2cd), file=destination)


def test_output():
    """Indirect test of the output for regression."""
    tmp = NamedTemporaryFile(mode="w+")
    generate_graph(tmp)
    tmp.file.seek(0)
    with open(_REPORT) as report:
        for line in report:
            yield assert_equal, line, tmp.readline()
