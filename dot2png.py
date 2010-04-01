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
        for (fn_dot, path_dot) in find(path, patt_dot):
            path_png = os.path.splitext(path_dot)[0] + '.png'
            cmd = 'dot -Tpng %s -o %s'%(path_dot, path_png)
            print cmd
            status, output = commands.getstatusoutput(cmd)
            if(len(output)):
                print output

if __name__ == '__main__':
    paths = sys.argv[1:]
    if(len(paths)==0):
        print 'Usage: dot2png.py <path-to-dot>'
        sys.exit()
    convert(paths)

