#!/usr/bin/env python2.6
'''
Convert Graphviz dot files to PNG files.
Requires:
1) Python 2.6
2) Graphviz from http://www.graphviz.org/
'''

import os.path
import os
import re
import commands
import sys
from optparse import OptionParser

patt_dot = re.compile('(?i).*\.dot$')

def find(path, fnmatcher):
    if(os.path.isfile(path)):
        fn = os.path.basename(path)
        m = fnmatcher.match(fn)
        if m:
            yield (fn, path)
        return
    for root,dirs,files in os.walk(path):
        for entry in files:
            m = fnmatcher.match(entry)
            if m:
                full_path = os.path.join(root, entry)
                yield (entry, full_path)

def convert(paths):
    for path in paths:
        if(not os.path.exists(path)):
            print '%s does not exist.'%path
            return
    for path in paths:
        for (fn_dot, path_dot) in find(path, patt_dot):
            path_png = os.path.splitext(path_dot)[0] + '.png'
            cmd = 'dot -Tpng %s -o %s'%(path_dot, path_png)
            print cmd
            status, output = commands.getstatusoutput(cmd)
            if(len(output)):
                print output

def main():
    usage = '''dot2png.py is designed for recursively converting Graphviz dot files under specified paths to PNG files.
dot2png.py [dot_paths] '''
    parser = OptionParser(usage)
    (options,args) = parser.parse_args()
    if(len(args)==0):
        parser.error('at least one path expected.')
    convert(args)

if __name__ == '__main__':
    main()
