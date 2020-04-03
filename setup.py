# encoding: utf-8
'''
Created on 2020-04-03 15:40:13
generate_setup tool

@author: nonamepand

* create package: python setup.py sdist --format=zip
'''
from __future__ import unicode_literals, absolute_import, print_function
import os
import sys
import traceback
import json

from setuptools import setup

os.environ["DISTUTILS_DEBUG"] = "True"

try:
    string_types = basestring  # @UndefinedVariable
except NameError:
    string_types = str

class Path(str):
    # utility class for file path and file operations
    def __new__(self, *paths): return str.__new__(self, os.path.join(*paths))

    def join(self, *paths): return self.__class__(self, *paths)

    def read(self, mode = "r", default = None):
        try:
            with open(self, mode = mode) as fp:
                return fp.read()
        except:
            return default

    def write(self, content, mode = "w"):
        with open(self, mode = mode) as fp:
            fp.write(content)

    @property
    def abspath(self): return self.__class__(os.path.abspath(self))
    @property
    def isfile(self): return os.path.isfile(self)
    @property
    def isdir(self): return os.path.isdir(self)

    def iterate(self, files = True, dirs = True, deep = False):
        def gen(root):
            for elm in os.listdir(root):
                r = root.join(elm).abspath
                if files and r.isfile:
                    yield r
                if r.isdir:
                    if dirs:
                        yield r
                    if deep:
                        for sub in r.iterate(files = files, dirs = dirs, deep = True):
                            yield sub
        for ent in gen(self):
            yield ent

class DistributionVersion(object):
    # distribution versions
    canonical_version = "0.0.0"
    build_version = 0
    def __init__(self, **fields): self.__dict__.update(fields)

    def __str__(self):
        return str(self.__dict__)
    __repr__ = __str__

    def update(self, **kwds):
        self.__dict__.update(kwds)
        return self

    def strictVersion(self):
        return "%s.%s" % (self.canonical_version, self.build_version)

    def filebasename(self):
        return "%s-%s.zip" % (dist_name, self.strictVersion())

    def findCanonicalVersionDist(self):
        return current_dir.join("dist", self.filebasename())

dist_name = "AMP"
current_dir = Path(os.path.dirname(__file__)).abspath
src_dir = current_dir.join(".")
egginfo_dir = current_dir.join("%s.egg-info" % dist_name)
if not egginfo_dir.isdir:
    os.makedirs(egginfo_dir)
distver_filename = "DistributionInfo.json"
distver_file = current_dir.join(distver_filename)
egginfo_distver_file = egginfo_dir.join(distver_filename)
README = current_dir.join("README.rst").read(default = "")

if "sdist" in sys.argv:
    # making source dist package.
    distver = distver_file.read()
    if not distver:
        distver = dict(
            canonical_version = "0.0.0",
            build_version = 0,
        )
    else:
        distver = json.loads(distver)

    distver = DistributionVersion(**distver)

    # remove old package
    if distver.findCanonicalVersionDist().isfile:
        os.remove(distver.findCanonicalVersionDist())
        # increments build version when old packages exists
        distver.build_version += 1
    else:
        # missing latest sdist version package,
        # stay distver.build_version
        pass
    # save states into distver file and dist. package dir
    unload_distver = json.dumps(vars(distver))
    distver_file.write(unload_distver)
    egginfo_distver_file.write(unload_distver)

    dist_strict_version = distver.strictVersion()
else:
    # installing source dist package.
    distver = DistributionVersion(**json.loads(egginfo_dir.join(distver_filename).read(default = "{}")))
    dist_strict_version = distver.strictVersion()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(current_dir))

def walkpackages(
        rootpath,
        include_fqns = [".*"],
        exclude_fqns = [],
        pred = (lambda path, modname: True)
    ):
    def _toregexs_(alist):
        import re
        return [
            re.compile(elm).findall if isinstance(elm, string_types) else elm
            for elm in alist
        ]
    includes = _toregexs_(include_fqns)
    excludes = _toregexs_(exclude_fqns)
    def bypath():
        apath = Path(rootpath).abspath
        if not apath.isdir:
            return
        subpathoffset = len(apath) + len(os.sep)
        for d in apath.iterate(files = False, dirs = True, deep = True):
            if d.join("__init__.py").isfile:
                module_name = d[subpathoffset:].replace(os.sep, ".")
                if any(f(module_name) for f in includes):
                    if any(f(module_name) for f in excludes):
                        continue
                    if pred and pred(d, module_name):
                        yield module_name
    return list(bypath())

# remove old SOURCES.txt
sources = egginfo_dir.join("SOURCES.txt")
if sources.isfile:
    os.remove(sources)
try:
    setup(
        name = dist_name,
        version = dist_strict_version,
        packages = walkpackages(
            src_dir,
            exclude_fqns = ["unused", "^test", "migrations"],
            pred = (lambda path, modname: not path.join("skip-packaging").isfile)
        ),
        include_package_data = True,
        license = 'MIT',
        description = "Application module packaging tools",
        long_description = README,
        author = 'nonamepand',
        author_email = '',
        zip_safe = True,
        install_requires = [],
        classifiers = [
            'Intended Audience :: Developers',
            'License :: MIT',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.6',
        ],
    )
except:
    traceback.print_exc()
