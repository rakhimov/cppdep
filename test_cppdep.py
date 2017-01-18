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

"""Tests for the analysis facilities."""

from __future__ import absolute_import

import platform

import pytest

import cppdep


@pytest.mark.parametrize('filename,expected',
                         [('path.cc', 'path'), ('path.', 'path'),
                          ('.path', '.path'), ('path', 'path'),
                          ('very/long/path.h', 'very/long/path'),
                          ('./.././path.cc', './.././path')])
def test_strip_ext(filename, expected):
    """Test extraction of file name."""
    assert cppdep.strip_ext(filename) == expected


@pytest.mark.skipif(platform.system() == 'Windows', reason='non-POSIX')
@pytest.mark.parametrize('path,paths,expected',
                         [('root', ('../file',), 'file'),
                          ('root', ('file',), 'root/file'),
                          ('.', ('./file',), 'file')])
def test_path_normjoin_posix(path, paths, expected):
    """Test the normalized join of paths on POSIX systems."""
    assert cppdep.path_normjoin(path, *paths) == expected


@pytest.mark.skipif(platform.system() != 'Windows', reason='non-DOS')
@pytest.mark.parametrize('path,paths,expected',
                         [(r'C:\root', (r'..\file',), r'C:\file'),
                          ('root', ('file',), r'root\file'),
                          ('.', (r'.\file',), 'file'),
                          ('root\\', ('dir/file',), r'root\dir\file')])
def test_path_normjoin_dos(path, paths, expected):
    """Test the normalized join of paths on DOS systems."""
    assert cppdep.path_normjoin(path, *paths) == expected


@pytest.mark.skipif(platform.system() == 'Windows',
                    reason='The same logic with different path separators.')
@pytest.mark.parametrize('paths,expected',
                         [(['/path', '/path/file', '/path/file2'], '/path'),
                          (['/path', '/dir'], '/'),
                          (['/path/file', '/pa'], '/'),
                          (['/path/dir/file', '/path/dir1/file'], '/path'),
                          (['/path/dir/', '/path/dir/file'], '/path/dir')])
def test_path_common_posix(paths, expected):
    """Test common directory for paths."""
    assert cppdep.path_common(paths) == expected


@pytest.mark.skipif(platform.system() == 'Windows',
                    reason='The same logic with different path separators.')
@pytest.mark.parametrize('parent,child,expected',
                         [('/dir', '/dir/file', True),
                          ('/dir/file', '/dir', False),
                          ('/dir/', '/dir/file', True),
                          ('/di', '/dir/file', False),
                          ('/', '/dir/file', True),
                          ('/dir', '/dir/dir2/file', True),
                          ('/tar', '/dir/file', False),
                          ('/dir', '/dir', True)])
def test_path_isancestor(parent, child, expected):
    """Test proper ancestor directory check for paths."""
    assert cppdep.path_isancestor(parent, child) == expected


@pytest.mark.skipif(platform.system() != 'Windows', reason='POSIX is noop.')
@pytest.mark.parametrize('path,expected',
                         [('file', 'file'), ('/dir/file', '/dir/file'),
                          (r'\dir\file', '/dir/file'),
                          (r'/dir\file', '/dir/file')])
def test_path_to_posix_sep(path, expected):
    """Test POSIX separator normalization for DOS paths."""
    assert cppdep.path_to_posix_sep(path) == expected
