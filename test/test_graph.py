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

from __future__ import print_function, absolute_import

from tempfile import NamedTemporaryFile
from nose.tools import assert_equal

import graph


_REPORT = "./test/graph_report.txt"


def output_graph(digraph, destination):
    """Prints the graph nodes and edges."""
    print('nodes(%d): ' % digraph.number_of_nodes(),
          ' '.join(str(x) for x in sorted(digraph)), file=destination)
    print('edges(%d): ' % digraph.number_of_edges(),
          ' '.join(sorted(str(x[0]) + '->' + str(x[1])
                          for x in digraph.edges())),
          file=destination)


def generate_graph(destination):
    """Prints the graph and metrics into the specified destination."""
    dependency_graph = graph.Graph([])
    digraph = dependency_graph.digraph
    edges1 = [(1, 2), (2, 4), (2, 6), (6, 2), (6, 7), (7, 6)]
    edges2 = [(1, 3), (1, 5), (3, 4), (3, 5), (3, 8), (8, 9), (9, 3)]
    edges3 = [(10, 11), (10, 12), (11, 12), (12, 11)]
    digraph.add_edges_from(edges1)
    digraph.add_edges_from(edges2)
    digraph.add_edges_from(edges3)
    print('=' * 80, file=destination)
    print('original digraph:', file=destination)
    output_graph(digraph, destination)
    dependency_graph.analyze()
    print('=' * 80, file=destination)
    print('after minimization:', file=destination)
    output_graph(digraph, destination)
    print('=' * 80, file=destination)
    print('cycles:', file=destination)
    for cycle in sorted(dependency_graph.cycles, key=min):
        print('\ncycle %d:' % min(cycle), file=destination)
        output_graph(cycle, destination)


def test_output():
    """Indirect test of the output for regression."""
    tmp = NamedTemporaryFile(mode="w+")
    generate_graph(tmp)
    tmp.file.seek(0)
    with open(_REPORT) as report:
        for line in report:
            yield assert_equal, line, tmp.readline()
