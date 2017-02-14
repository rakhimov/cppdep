#!/usr/bin/env python
#
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

"""The command-line entry point for the package."""

from __future__ import print_function, absolute_import

import argparse as ap
import logging
import sys

from yaml import YAMLError
from pykwalify.core import SchemaError

from cppdep import cppdep


def main(argv=None):
    """Runs the dependency analysis and prints results and graphs."""
    parser = ap.ArgumentParser(description=cppdep.__doc__,
                               formatter_class=ap.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--version', action='store_true', default=False,
                        help='show the version information and exit')
    parser.add_argument('-c', '--config', default='.cppdep.yml',
                        help="""a YAML file which describes
                        the source code structure of a C/C++ project""")
    parser.add_argument('-l', action='store_true', default=False,
                        help='list reduced dependencies of nodes')
    parser.add_argument('-L', action='store_true', default=False,
                        help='list unreduced dependencies of nodes')
    parser.add_argument('-o', '--output', metavar='path', help='output file')
    args = parser.parse_args(argv)
    if args.version:
        print(cppdep.VERSION)
        return

    def _die(head, body):
        logging.error(str('%s:\n%s' % (head, str(body))))
        sys.exit(1)

    try:
        analysis = cppdep.DependencyAnalysis(args.config)
        printer = get_printer(args.output)
        analysis.analyze(printer, args)
    except IOError as err:
        _die('IO Error', err)
    except YAMLError as err:
        _die('Malformed Configuration File', err)
    except SchemaError as err:
        _die('Configuration File Validity Error', err)
    except cppdep.InvalidArgumentError as err:
        _die('Invalid Argument Error', err)
    except cppdep.AnalysisError as err:
        _die('Analysis (Configuration) Error', err)


def get_printer(file_path=None):
    """Returns printer for the report."""
    destination = open(file_path, 'w') if file_path else sys.stdout

    def _print(*args):
        print(*args, file=destination)

    return _print


if __name__ == "__main__":
    main()
