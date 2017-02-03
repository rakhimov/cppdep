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

from __future__ import print_function, absolute_import

import pytest

from cppdep import graph

#pylint: disable=redefined-outer-name

@pytest.fixture()
def small_graph():
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


def test_graph_init(small_graph):
    """Test the graph creation."""
    digraph = small_graph.digraph
    assert set(digraph) == set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    assert set(digraph.edges()) == set([(1, 2), (1, 3), (1, 5), (10, 11),
                                        (10, 12), (11, 12), (12, 11), (2, 4),
                                        (2, 6), (3, 4), (3, 5), (3, 8), (6, 2),
                                        (6, 7), (7, 6), (8, 9), (9, 3)])


@pytest.fixture()
def dep_graph(small_graph):
    """Sets up the analyzed graph."""
    small_graph.analyze()
    return small_graph


def test_graph_minimal(dep_graph):
    """Test the graph after minimization."""
    digraph = dep_graph.digraph
    assert set(digraph) == set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    assert set(digraph.edges()) == set([(1, 2), (1, 3), (10, 11),
                                        (10, 12), (11, 12), (12, 11), (2, 4),
                                        (2, 6), (3, 4), (3, 5), (3, 8), (6, 2),
                                        (6, 7), (7, 6), (8, 9), (9, 3)])


def test_graph_cycles(dep_graph):
    """Test graph cycles after minimization/analysis."""
    expected_cycles = {(2, 6, 7): set([(2, 6), (6, 2), (6, 7), (7, 6)]),
                       (3, 8, 9): set([(3, 8), (8, 9), (9, 3)]),
                       (11, 12): set([(11, 12), (12, 11)])}
    graph_cycles = {tuple(sorted(cycle)): set(cycle.edges())
                    for cycle in dep_graph.cycles}
    assert graph_cycles == expected_cycles


def test_print_cycles(dep_graph, capsys):
    """Test report of cycles."""
    dep_graph.print_cycles(print)
    out, _ = capsys.readouterr()
    assert out.split('\n') == ['=' * 80, '3 cycles detected:', '',
                               'cycle #0 (2 nodes): 11, 12',
                               'cycle #0 (2 edges): 11->12 12->11', '',
                               'cycle #1 (3 nodes): 2, 6, 7',
                               'cycle #1 (4 edges): 2->6 6->2 6->7 7->6', '',
                               'cycle #2 (3 nodes): 3, 8, 9',
                               'cycle #2 (3 edges): 3->8 8->9 9->3', '', '']


def test_print_levels(dep_graph, capsys):
    """Test the reporting of node levels."""
    dep_graph.print_levels(print)
    out, _ = capsys.readouterr()
    assert out.split('\n') == ['=' * 80, '5 level(s):', '', 'level 0:',
                               'level 1:', '\t4', '\t5',
                               'level 2:', '\t11 <0>', '\t12 <0>',
                               'level 3:', '\t10',
                               'level 4:', '\t2 <1>', '\t6 <1>', '\t7 <1>',
                               '\t3 <2>', '\t8 <2>', '\t9 <2>',
                               'level 5:', '\t1', '']


def test_print_levels_with_deps(dep_graph, capsys):
    """Test the reporting of node levels with reduced dependencies."""
    dep_graph.print_levels(print, reduced_dependencies=True)
    out, _ = capsys.readouterr()
    assert out.split('\n') == ['=' * 80, '5 level(s):', '', 'level 0:',
                               'level 1:', '\t4', '\t5',
                               'level 2:',
                               '\t11 <0>', '\t\t2. 12 <0>',
                               '\t12 <0>', '\t\t2. 11 <0>',
                               'level 3:',
                               '\t10', '\t\t2. 11 <0>', '\t\t2. 12 <0>',
                               'level 4:',
                               '\t2 <1>', '\t\t1. 4', '\t\t4. 6 <1>',
                               '\t6 <1>', '\t\t4. 2 <1>', '\t\t4. 7 <1>',
                               '\t7 <1>', '\t\t4. 6 <1>',
                               '\t3 <2>', '\t\t1. 4', '\t\t1. 5',
                               '\t\t4. 8 <2>',
                               '\t8 <2>', '\t\t4. 9 <2>',
                               '\t9 <2>', '\t\t4. 3 <2>',
                               'level 5:',
                               '\t1', '\t\t4. 2 <1>', '\t\t4. 3 <2>', '']


def test_print_summary(dep_graph, capsys):
    """Test the summary report."""
    dep_graph.print_summary(print)
    out, _ = capsys.readouterr()
    assert out.split('\n') == ['=' * 80, 'SUMMARY:',
                               'Components: 12\t Cycles: 3\t Levels: 5',
                               'CCD: 45\t ACCD: 3.75\t NCCD: 1.25 '
                               '(typical range is [0.85, 1.10])', '']
