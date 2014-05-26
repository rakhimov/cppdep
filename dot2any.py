#!/usr/bin/env python2
'''
Convert Graphviz dot files to the specified format.
I select pdf as the default output format since it's the best one when concerning protablity, speed and size.
zhichyu@w-shpd-zcyu:~/sftw4ubuntu/cppdep$ ls -l |grep INETcttp.libCallRecord_orig
-rw-r--r-- 1 zhichyu zhichyu    26731 2010-04-02 14:28 INETcttp.libCallRecord_orig.dia
-rw-r--r-- 1 zhichyu zhichyu    11239 2010-04-02 13:42 INETcttp.libCallRecord_orig.dot
-rw-r--r-- 1 zhichyu zhichyu    98468 2010-04-02 14:22 INETcttp.libCallRecord_orig.fig
-rw-r--r-- 1 zhichyu zhichyu   980623 2010-04-02 14:27 INETcttp.libCallRecord_orig.jpeg
-rw-r--r-- 1 zhichyu zhichyu    28150 2010-04-02 14:30 INETcttp.libCallRecord_orig.pdf
-rw-r--r-- 1 zhichyu zhichyu  1837563 2010-04-02 13:50 INETcttp.libCallRecord_orig.png
-rw-r--r-- 1 zhichyu zhichyu   124614 2010-04-02 14:06 INETcttp.libCallRecord_orig.ps

Run "dot -v" to show all supported output formats.
zhichyu@w-shpd-zcyu:~/tmp/apps_cppdep$ dot -v
Activated plugin library: libgvplugin_pango.so.5
Using textlayout: textlayout:cairo
Activated plugin library: libgvplugin_dot_layout.so.5
Using layout: dot:dot_layout
Activated plugin library: libgvplugin_core.so.5
Using render: dot:core
Using device: dot:dot:core
The plugin configuration file:
	/usr/lib/graphviz/config4
		was successfully loaded.
    render	:  cairo dot fig gd map ps svg tk vml vrml xdot
    layout	:  circo dot fdp neato nop nop1 nop2 twopi
    textlayout	:  textlayout
    device	:  canon cmap cmapx cmapx_np dia dot eps fig gd gd2 gif hpgl imap imap_np ismap jpe jpeg jpg mif mp pcl pdf pic plain plain-ext png ps ps2 svg svgz tk vml vmlz vrml vtx wbmp xdot xlib
    loadimage	:  (lib) gd gd2 gif jpe jpeg jpg png ps svg


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

def convert(paths, format):
    for path in paths:
        if(not os.path.exists(path)):
            print '%s does not exist.'%path
            return
    for path in paths:
        for (fn_dot, path_dot) in find(path, patt_dot):
            basename = os.path.splitext(path_dot)[0]
            cmd = 'dot -T%s %s -o %s.%s'%(format, path_dot, basename, format)
            print cmd
            status, output = commands.getstatusoutput(cmd)
            if(len(output)):
                print output

def main():
    usage = '''dot2any.py is designed for recursively converting Graphviz dot files under specified paths to the specified format. The default output format is pdf.
dot2any.py [-T lang] [dot_paths] '''
    parser = OptionParser(usage)
    parser.add_option('-T', dest='output_format', default='pdf', help='set output format. pdf is used by default.')
    (options,args) = parser.parse_args()
    if(len(args)==0):
        parser.error('at least one path expected.')
    good_formats = 'fig jpeg pdf png ps'.split()
    if(options.output_format not in good_formats):
        parser.error('%s is an invalid output format, or it is no better than following formats: %s'%(options.output_format, ' '.join(good_formats)))
    convert(args, options.output_format)

if __name__ == '__main__':
    main()
