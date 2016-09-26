#!/usr/bin/env python
'''Converts Graphviz dot files to the specified format recursively.'''

from __future__ import print_function, absolute_import
import sys
import os
import re
from subprocess import call
import argparse as ap


_PATT_DOT = re.compile(r'(?i).*\.dot$')


class Dot2AnyError(Exception):
    '''Problems with conversion.'''

    pass


def find(path, fnmatcher):
    if os.path.isfile(path):
        fn = os.path.basename(path)
        if fnmatcher.match(fn):
            yield (fn, path)
        return
    for root, _, files in os.walk(path):
        for entry in files:
            if fnmatcher.match(entry):
                full_path = os.path.join(root, entry)
                yield (entry, full_path)


def convert(paths, out_format):
    for path in paths:
        for _, path_dot in find(path, _PATT_DOT):
            basename = os.path.splitext(path_dot)[0]
            cmd = ['dot', '-T' + out_format, path_dot,
                   '-o', basename + '.' + out_format]
            print(cmd)
            if call(cmd):
                raise Dot2AnyError("dot failure")


def check_paths(paths):
    '''Validates existence of paths.

    Args:
        paths: A collection of paths.

    Raises:
        IOError: The given paths may not exist.
    '''
    for path in paths:
        if not os.path.exists(path):
            raise IOError('%s does not exist.' % path)


def main():
    '''
    I select pdf as the default output format
    since it's the best one when concerning portability, speed and size.
    Run "dot -v" to show all supported output formats.
    '''
    parser = ap.ArgumentParser(description=__doc__,
                               formatter_class=ap.ArgumentDefaultsHelpFormatter)
    good_formats = 'fig jpeg pdf png ps'.split()
    parser.add_argument('-T', dest='output_format', default='pdf',
                        help='set output format %s' % str(good_formats))
    parser.add_argument('dot_file', nargs="+", type=str,
                        help='input dot files')
    args = parser.parse_args()
    if args.output_format not in good_formats:
        raise ap.ArgumentTypeError('%s is an invalid output format: %s' %
                                   args.output_format)
    check_paths(args.dot_file)
    convert(args.dot_file, args.output_format)

if __name__ == '__main__':
    try:
        main()
    except ap.ArgumentTypeError as err:
        print("Argument Error:\n" + str(err))
        sys.exit(2)
    except IOError as err:
        print("IO Error:\n" + str(err))
        sys.exit(1)
    except Dot2AnyError as err:
        print("Conversion error:\n" + str(err))
