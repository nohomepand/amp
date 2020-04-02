# encoding: utf-8
'''
Created on 2020/04/01

@author: oreyou
'''
from __future__ import absolute_import, print_function, unicode_literals

import json
import os
import sys
import zipfile

from amp.core import utils, template_bootstrap


class SiteConfiguration(utils.AutoDict):
    class Default:
        packages = []
        outputs = None
    
    @classmethod
    def autoconf(
            cls,
            sys_path = None,
            python_path = None,
            env_path = None,
        ):
        """
        sys.path等から自動構成
        """
        packages = []
        packages.append(CommentLine(message = "begin sys.path"))
        for path in map(utils.FilePath.ensure, sys.path if sys_path is None else sys_path):
            path = path.abspath()
            if not path.exists():
                continue
            if "site-packages" in path:
                packages.append(PythonSitePackageConfig(root = path))
            else:
                pb = PythonBasePackageConfig(root = path)
                pb.excludes.append(".*/site-packages/.*")
                packages.append(pb)
        packages.append(CommentLine(message = "begin $PYTHONPATH"))
        for path in map(utils.FilePath.ensure, os.environ.get("PYTHONPATH", "").split(os.pathsep) if python_path is None else python_path):
            path = path.abspath()
            if not path.exists():
                continue
            pb = PythonBasePackageConfig(root = path)
            pb.excludes.append(".*/site-packages/.*")
            packages.append(pb)
        packages.append(CommentLine(message = "begin $PATH"))
        for path in map(utils.FilePath.ensure, os.environ.get("PATH", "").split(os.pathsep) if env_path is None else env_path):
            path = path.abspath()
            if not path.exists():
                continue
            if path.isfile():
                packages.append(DependentPackageConfig(subdir = False, root = path))
            elif path.isdir():
                packages.append(DependentPackageConfig(subdir = False, root = path))
        return cls(packages = packages)
    
    def iter_files(
            self,
            targets = object,
        ):
        for pkg in self.packages:
            if not isinstance(pkg, targets):
                continue
            for ent in pkg.iter_files():
                yield ent
    
    def dump(
            self,
            targets = object,
        ):
        with DumpObject(self) as dumpobj: 
            for pkg in self.packages:
                if not isinstance(pkg, targets):
                    continue
                pkg.dump_to(dumpobj)
            return dumpobj

@SiteConfiguration.register("outputs")
class OutputConfiguration(utils.AutoDict):
    class Default:
        override = True
        modules = "py"
        extmodules = "pyext"
        depends = "dep"
        distname = "dist.json"
        filename = "out.zip"
    
    def configured(self):
        assert self.modules, "No `modules` configuration"
        assert self.extmodules, "No `extmodules` configuration"
        assert self.depends, "No `depends` configuration"
        assert self.distname, "No `distname` configuration"
        assert self.filename, "No `filename` configuration"

@SiteConfiguration.register("packages")
class PackagesConfiguration(utils.AutoDict):
    class Default:
        items = []

class PackingConfigration(utils.AutoDict):
    class Default:
        type = None
        root = None
        includes = []
        excludes = []
    
    def iter_files(
            self
        ):
        assert self.root
        root = utils.FilePath(self.root)
        inc, exc = utils.PathMatcher(*self.includes), utils.PathMatcher(*self.excludes)
        consists = (lambda path: not (exc(path) and not inc(path)))
        if root.isdir():
            for ent in root.list(lambda p, depth: depth == 1 or p.join("__init__.py").isfile()):
                if consists(ent) and not ent.isdir():
                    yield ent
        elif root.isfile():
            if consists(root):
                yield root
    
    def dump_to(self, dumpobj):
        assert isinstance(dumpobj, DumpObject)

@PackagesConfiguration.register("comment")
class CommentLine(PackingConfigration):
    class Default:
        message = ""
    
    def iter_files(self):
        return []

class PythonPackingConfiguration(PackingConfigration):
    class Default(PackingConfigration):
        includes = [
            # ".*\\.py$", ".*\\.pyd$"
        ]
        excludes = [
            ".*\\.pyc$",
            ".*\\.pdb$",
            ".*\\.chm$", # conda `compiled html` doc
            ".*\\.egg-info.*$",
        ]
        zipsafe = [".*\\.py$"]
    
    def dump_to(self, dumpobj):
        zipsafe = utils.PathMatcher(*self.zipsafe)
        for ent in self.iter_files():
            assert isinstance(ent, utils.FilePath)
            dumpobj.write_python(ent, ent.relpath(self.root), zipsafe = zipsafe(ent))

@PackagesConfiguration.register("python-base")
class PythonBasePackageConfig(PythonPackingConfiguration):
    class Default(PythonPackingConfiguration.Default):
        pass

@PackagesConfiguration.register("site-packages")
class PythonSitePackageConfig(PythonPackingConfiguration):
    class Default(PythonPackingConfiguration.Default):
        pass

@PackagesConfiguration.register("depends")
class DependentPackageConfig(PackingConfigration):
    class Default(PackingConfigration.Default):
        subdir = False
    
    def iter_files(self):
        assert self.root
        root = utils.FilePath(self.root)
        inc, exc = utils.PathMatcher(*self.includes), utils.PathMatcher(*self.excludes)
        consists = (lambda path: not (exc(path) and not inc(path)))
        if root.isdir():
            for ent in root.list(self.subdir):
                if consists(ent):
                    yield ent
        elif root.isfile():
            if consists(root):
                yield root
    
    def dump_to(self, dumpobj):
        for ent in self.iter_files():
            assert isinstance(ent, utils.FilePath)
            dumpobj.write_depends(ent, ent.relpath(self.root))

class DumpObject(utils.Dict):
        
    def __init__(self, siteconf):
        assert isinstance(siteconf, SiteConfiguration)
        assert siteconf.outputs, "`outputs` is not configured: siteconf.outputs=%s" % siteconf.outputs
        siteconf.outputs.configured()
        self.siteconf = siteconf
        self.modules = utils.ZipOutput(compress = zipfile.ZIP_STORED)
        self.extmodules = utils.ZipOutput(compress = zipfile.ZIP_STORED)
        self.depends = utils.ZipOutput(compress = zipfile.ZIP_STORED)
        self.dist = utils.Dict(
            config = siteconf.outputs,
            py = utils.Dict(), # module, extmodules問わず
        )
        self.__closed = False
    
    def write_python(self, filename, modpath, zipsafe = True):
        zipsafe = bool(zipsafe)
        print("DumpObject.write_python %s -> %s(%s)" % (filename, modpath, zipsafe))
        self.dist.py[modpath] = zipsafe
        if zipsafe:
            self.modules.writefile(filename, modpath)
        else:
            self.extmodules.writefile(filename, modpath)
    
    def write_depends(self, filename, arcname):
        print("DumpObject.write_depends%s -> %s" % (filename, arcname))
        self.depends.writefile(filename, arcname)
    
    def __enter__(self):
        return self
    
    def __exit__(self, etype, einst, etrace):
        self.close()
    
    def close(self):
        if self.__closed:
            return
        self.__closed = True
        outputfilename = utils.FilePath.ensure(self.siteconf.outputs.filename)
        outputfilename.dirname().touch()
        with self.modules.closing() as modules, self.extmodules.closing() as extmodules, self.depends.closing() as depends:
            with utils.ZipOutput(outputfilename, zipfile.ZIP_DEFLATED) as zout:
                print("Adding %s" % self.siteconf.outputs.modules)
                zout.writefile(modules.filename, self.siteconf.outputs.modules)
                print("Adding %s" % self.siteconf.outputs.extmodules)
                zout.writefile(extmodules.filename, self.siteconf.outputs.extmodules)
                print("Adding %s" % self.siteconf.outputs.depends)
                zout.writefile(depends.filename, self.siteconf.outputs.depends)
                print("Adding %s" % self.siteconf.outputs.distname)
                with zout.open(self.siteconf.outputs.distname, "w") as fp:
                    json.dump(self.dist, fp, indent = 2)
                with zout.open("bootstrap.py", "wb") as fp:
                    src = template_bootstrap.BOOTSTRAP_PY.format(**self.siteconf.outputs)
                    fp.write(utils.ensure_bytes(src))
                with zout.open("winpshell.bat", "wb") as fp:
                    src = template_bootstrap.PSHELL_BAT.format(
                        python_executable = "python.exe",
                        bootstrap_py_name = "bootstrap.py",
                        **self.siteconf.outputs
                    )
                    fp.write(utils.ensure_bytes(src))
                    
        print("Finish %s" % self.siteconf.outputs.filename)

# if __name__ == '__main__':
#     px = SiteConfiguration.autoconf()
#     px.outputs = OutputConfiguration()
#     px.outputs.filename = "z:/out.zip"
#     px.dump(PythonPackingConfiguration)
#     
