# Copyright (C) 2017 Olzhas Rakhimov
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

"""Configuration facilities for cppdep tests with pytest."""

from cppdep import Include

#pylint: disable=invalid-name
def pytest_assertrepr_compare(op, left, right):
    """Custom assertion messages for cppdep classes."""
    if isinstance(left, Include) and isinstance(right, Include):
        if op in ('==', '!='):
            return ['Comparing Include directives:',
                    '    vals: %s %s %s' % (str(left),
                                            {'==': '!=', '!=': '=='}[op],
                                            str(right))]
