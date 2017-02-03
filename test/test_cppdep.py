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

import os
import platform
import re

import mock
import pytest

from cppdep import cppdep
from cppdep.cppdep import Include


def path_relpath_posix(path, root):
    """Returns relative path with posix separators."""
    return cppdep.path_to_posix_sep(os.path.relpath(path, root))


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
                          (['/path/dir/', '/path/dir/file'], '/path/dir'),
                          ([], ''), (['/dir'], '/dir'),
                          pytest.mark.xfail((['/dir/*'], '/dir'))])
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


@pytest.mark.parametrize('dictionary,element,default_value,expected',
                         [({'tag': 'value'}, 'tag', 'default', 'value'),
                          ({}, 'tag', 'default', 'default'),
                          ({'label': 'value'}, 'tag', 'default', 'default')])
def test_yaml_optional(dictionary, element, default_value, expected):
    """Test retrieval of an optional value from yaml configuration."""
    assert cppdep.yaml_optional(dictionary, element, default_value) == expected


@pytest.mark.parametrize(
    'dictionary,element,expected',
    [pytest.mark.xfail(({'tag': 'value'}, 'tag', ['value'])),
     ({'tag': ['value']}, 'tag', ['value']),
     ({}, 'tag', []),
     ({'label': 'value'}, 'tag', [])])
def test_yaml_optional_list(dictionary, element, expected):
    """Test special handling of optional lists in yaml configurations."""
    assert (cppdep.yaml_optional_list(dictionary, element) == expected)


@pytest.mark.parametrize(
    'include,expected',
    [(Include('vector', with_quotes=True), '"vector"'),
     (Include('vector', with_quotes=False), '<vector>'),
     (Include('dir/vector.h', with_quotes=False), '<dir/vector.h>'),
     (Include(r'dir\vector.h', with_quotes=False), r'<dir\vector.h>')])
def test_include_str(include, expected):
    """Tests proper string representation of include upon string conversion."""
    assert str(include) == expected


@pytest.mark.parametrize(
    'include_one,include_two',
    [(Include('vector', True), Include('vector', True)),
     (Include('vector', True), Include('vector', False)),
     (Include('./vector', True), Include('vector', True)),
     (Include('include/./vector', True), Include('include/vector', True))])
def test_include_eq(include_one, include_two):
    """Include equality and hash tests for storage in containers."""
    assert include_one == include_two
    assert hash(include_one) == hash(include_two)


def test_include_ne_impl():
    """Makes sure that __ne__ is implemented."""
    with mock.patch('cppdep.cppdep.Include.__eq__') as mock_eq:
        include_one = Include('vector', True)
        check = include_one != include_one
        assert mock_eq.called
        assert not check


@pytest.mark.parametrize(
    'include_one,include_two',
    [(Include('vector.hpp', True), Include('vector', True)),
     (Include('dir/vector', True), Include('include/vector', True))])
def test_include_neq(include_one, include_two):
    """__ne__ doesn't imply (not __eq__) in Python."""
    assert include_one != include_two


@pytest.mark.parametrize(
    'text,expected',
    [('#include <vector>', ['<vector>']),
     ('#include "vector"', ['"vector"']),
     ('#  include <vector>', ['<vector>']),
     ('#\tinclude <vector>', ['<vector>']),
     ('#include "vector.h"', ['"vector.h"']),
     ('#include "vector.h++"', ['"vector.h++"']),
     ('#include "vector.any"', ['"vector.any"']),
     ('#include "vector.hpp"', ['"vector.hpp"']),
     ('#include "vector.cpp"', ['"vector.cpp"']),
     ('#include "dir/vector.hpp"', ['"dir/vector.hpp"']),
     (r'#include "dir\vector.hpp"', [r'"dir\vector.hpp"']),
     ('#include "./vector"', ['"./vector"']),
     ('#include <./vector>', ['<./vector>']),
     ('#include <a>\n#include <b>', ['<a>', '<b>']),
     ('#include <b>\n#include <a>', ['<b>', '<a>']),
     ('#include <b> // a>', ['<b>']),
     ('#include "b" // a"', ['"b"']),
     ('#include <b> /* a> */', ['<b>']),
     ('#include "b" /* a" */', ['"b"']),
     ('#include ""', []),
     ('#include <>', []),
     ('//#include <vector>', []),
     ('/*#include <vector>*/', []),
     ('#import <vector>', []),
     ('include <vector>', []),
     ('#nclude <vector>', []),
     ('<vector>', []),
     ('"vector"', []),
     ('#<vector>', []),
     ('#include < vector>', []),
     ('#include <vector >', []),
     ('#include <vector nonconventional>', []),
     ('#include " vector"', []),
     ('#include "vector "', []),
     ('    #include <vector>', ['<vector>']),
     ('#include <vector>        ', ['<vector>']),
     ('some_code #include <vector>', []),
     ('#include <vector> some_code', ['<vector>']),
     pytest.mark.xfail(('#if 0\n#include <vector>\n#endif', [])),
     pytest.mark.xfail(('/*\n#include <vector>\n*/', [])),
     pytest.mark.xfail(('#define V  <vector>\n#include V\n', ['<vector>']))])
def test_include_grep(text, expected, tmpdir):
    """Tests the include directive search from a text."""
    src = tmpdir.join('include_grep')
    src.write(text)
    assert [str(x) for x in Include.grep(str(src))] == expected


@pytest.fixture()
def include_setup(tmpdir):
    """Sets up the system for include header search."""
    dirs = ['project1', 'external1', 'external2']
    files = [tmpdir.mkdir(x).join('header').write('') for x in dirs]
    return tmpdir, [os.path.join(str(tmpdir), x) for x in dirs]


#pylint: disable=redefined-outer-name
@pytest.mark.parametrize(
    'include,cwd,include_dirs,expected',
    [(Include('header', True), '.', [], None),
     (Include('header', True), 'project1', [], 'project1/header'),
     (Include('header', False), 'project1', [], None),
     (Include('header', True), 'project1', ['external2', 'external1'],
      'project1/header'),
     (Include('header', False), 'project1', ['external2', 'external1'],
      'external1/header'),
     (Include('header', False), 'project1', ['external1', 'external2'],
      'external2/header')])
def test_include_locate(include, cwd, include_dirs, expected, include_setup):
    """The search for header locations from include paths."""
    tmpdir, _ = include_setup
    abs_cwd = cppdep.path_normjoin(str(tmpdir), cwd)
    include_dirs = [cppdep.path_normjoin(str(tmpdir), x) for x in include_dirs]
    hpath, package = include.locate(abs_cwd, include_dirs, [])
    assert package is None
    assert include.hpath == hpath
    if expected is None:
        assert include.hpath is None
    else:
        assert include.hpath is not None
        assert path_relpath_posix(include.hpath, str(tmpdir)) == expected


@pytest.mark.parametrize(
    'include,cwd,include_patterns,expected',
    [(Include('header_foo', True), '.', [], (None, None)),
     (Include('header', True), '.', [('foo', 'header')], ('header', 'foo')),
     (Include('header', False), '.', [('foo', 'header')], ('header', 'foo')),
     (Include('header', False), 'project1', [('foo', 'header')],
      ('header', 'foo')),
     (Include('header', False), '.', [('foo', 'header'), ('bar', 'header')],
      ('header', 'foo')),
     (Include('header', False), '.', [('bar', 'header'), ('foo', 'header')],
      ('header', 'bar')),
     (Include('header_foo', False), '.', [('foo', 'header$')], (None, None)),
     (Include('header_foo', False), '.', [('foo', 'header')],
      ('header_foo', 'foo')),
     (Include('header_foo', False), '.', [('foo', 'header_foo')],
      ('header_foo', 'foo'))])
def test_include_locate_pattern(include, cwd, include_patterns, expected,
                                include_setup):
    """Pattern based include header location."""
    tmpdir, include_dirs = include_setup
    abs_cwd = cppdep.path_normjoin(str(tmpdir), cwd)
    include_patterns = [(x, [re.compile(y)]) for x, y in include_patterns]
    assert include.locate(abs_cwd, include_dirs, include_patterns) == expected


@pytest.mark.parametrize('hpath,cpath',
                         [('header', None), (None, 'source'),
                          ('header', 'source')])
def test_component_init(hpath, cpath, tmpdir, monkeypatch):
    """Component construction from header and implementation files."""
    mock_warn = mock.MagicMock(spec=cppdep.warn)
    monkeypatch.setattr(cppdep, 'warn', mock_warn)
    package = mock.MagicMock(spec=cppdep.Package)
    package.name = 'mock_package'
    package.group = mock.MagicMock(spec=cppdep.PackageGroup)
    package.group.name = 'mock_group'
    package.root = str(tmpdir)
    if hpath:
        tmpdir.join(hpath).write('')
        hpath = cppdep.path_normjoin(str(tmpdir), hpath)
    if cpath:
        tmpdir.join(cpath).write('')
        cpath = cppdep.path_normjoin(str(tmpdir), cpath)
    component = cppdep.Component(hpath, cpath, package)
    assert (component.name ==
            path_relpath_posix(cppdep.strip_ext(cpath or hpath), str(tmpdir)))
    assert str(component) == component.name
    assert component.package == package
    assert component.hpath == hpath
    assert component.cpath == cpath
    assert hpath or mock_warn.called


@pytest.mark.parametrize('filename,is_header',
                         [('', None), ('.file', None), ('header', True),
                          ('head.er', None), ('header.h', True),
                          ('head.er.h', None), ('dir/header.h', None),
                          ('header.hpp', True), ('header.h++', True),
                          ('header.hh', True), ('header.hxx', True),
                          ('src.c', False), ('src.cc', False),
                          ('src.c++', False), ('src.cxx', False),
                          ('src.cpp', False), ('src.java', None),
                          ('unconvetional header.hpp', None)])
def test_package_src_regex(filename, is_header):
    """Test the regex for matching and gathering C/C++ header/source files."""
    src_match = cppdep.Package._RE_SRC.match(filename)
    if is_header is None:
        assert not src_match
    elif is_header:
        assert src_match.group('h') is not None
    else:
        assert src_match.group('c') is not None
