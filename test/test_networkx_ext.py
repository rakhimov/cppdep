# Copyright (C) 2016 cppdep developers
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

from subprocess import call
from tempfile import NamedTemporaryFile

from nose.tools import assert_equal


_REPORT = "./test/networkx_ext_report.txt"


def test_output():
    """Indirect test of the output for regression."""
    tmp = NamedTemporaryFile()
    call(["./networkx_ext.py"], stdout=tmp)
    tmp.file.seek(0)
    with open(_REPORT) as report:
        for line in report:
            yield assert_equal, line, tmp.readline()
