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

"""Tests for graph extension functions."""

from __future__ import absolute_import

import pytest

import graph


@pytest.fixture()
def dep_graph():
    """A small dependency graph with multiple cycles."""
    dependency_graph = graph.Graph([])
    digraph = dependency_graph.digraph
    edges1 = [(1, 2), (2, 4), (2, 6), (6, 2), (6, 7), (7, 6)]
    edges2 = [(1, 3), (1, 5), (3, 4), (3, 5), (3, 8), (8, 9), (9, 3)]
    edges3 = [(10, 11), (10, 12), (11, 12), (12, 11)]
    digraph.add_edges_from(edges1)
    digraph.add_edges_from(edges2)
    digraph.add_edges_from(edges3)
    return dependency_graph


def test_graph_init(dep_graph):
    """Test the graph creation."""
    digraph = dep_graph.digraph
    assert set(digraph) == set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    assert set(digraph.edges()) == set([(1, 2), (1, 3), (1, 5), (10, 11),
                                        (10, 12), (11, 12), (12, 11), (2, 4),
                                        (2, 6), (3, 4), (3, 5), (3, 8), (6, 2),
                                        (6, 7), (7, 6), (8, 9), (9, 3)])


def test_graph_minimal(dep_graph):
    """Test the graph after minimization."""
    dep_graph.analyze()
    digraph = dep_graph.digraph
    assert set(digraph) == set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    assert set(digraph.edges()) == set([(1, 2), (1, 3), (10, 11),
                                        (10, 12), (11, 12), (12, 11), (2, 4),
                                        (2, 6), (3, 4), (3, 5), (3, 8), (6, 2),
                                        (6, 7), (7, 6), (8, 9), (9, 3)])


def test_graph_cycles(dep_graph):
    """Test graph cycles after minimization/analysis."""
    dep_graph.analyze()
    expected_cycles = {(2, 6, 7): set([(2, 6), (6, 2), (6, 7), (7, 6)]),
                       (3, 8, 9): set([(3, 8), (8, 9), (9, 3)]),
                       (11, 12): set([(11, 12), (12, 11)])}
    graph_cycles = {tuple(sorted(cycle)): set(cycle.edges())
                    for cycle in dep_graph.cycles}
    assert graph_cycles == expected_cycles
