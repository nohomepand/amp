# encoding: utf-8
'''
Created on 2020/04/01

@author: oreyou

* AMPでパッケージングされるファイルの収集・分類・列挙を行うモジュール
'''
from __future__ import absolute_import, print_function, unicode_literals

import json
import os
import sys
import zipfile

from amp.core import utils, template_bootstrap
from amp.bootup import blobstore

class SiteConfiguration(utils.AutoDict):
    """
    パッケージングされるファイルの収集のための、収集対象の構成を表すもの
    """
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
        sys.path等からこのクラスのインスタンスを生成する
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
        """
        収集対象のファイルを列挙する
        """
        for pkg in self.packages:
            if not isinstance(pkg, targets):
                continue
            for ent in pkg.iter_files():
                yield ent
    
    def dump(
            self,
            targets = object,
            storage_class = "ZipResourceComposer",
        ):
        """
        収集対象のファイルを分類しつつパッケージを生成する
        """
        storage_class = globals()[storage_class] if isinstance(storage_class, utils.string_types) else storage_class
        with storage_class(self) as storage: 
            for pkg in self.packages:
                if not isinstance(pkg, targets):
                    continue
                pkg.dump_to(storage)
            return storage

@SiteConfiguration.register("outputs")
class OutputConfiguration(utils.AutoDict):
    """
    パッケージングの出力の構成を表すもの
    """
    class Default:
        override = True
        modules = "py"
        distname = "dist.json"
        filename = "out.zip"
    
    def configured(self):
        assert self.modules, "No `modules` configuration"
        assert self.distname, "No `distname` configuration"
        assert self.filename, "No `filename` configuration"

@SiteConfiguration.register("packages")
class PackagesConfiguration(utils.AutoDict):
    """
    パッケージングの収集される要素のリストを表すもの
    """
    class Default:
        items = []

class PackingConfigration(utils.AutoDict):
    """
    Pythonモジュールや依存ファイルの収集と分類を表す構成の基底クラス
    """
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
        assert isinstance(dumpobj, ZipResourceComposer)

@PackagesConfiguration.register("comment")
class CommentLine(PackingConfigration):
    """
    (internal) PackagesConfigurationの構成の一部としてコメント要素を表すもの
    """
    class Default:
        message = ""
    
    def iter_files(self):
        return []

class PythonPackingConfiguration(PackingConfigration):
    """
    Pythonモジュールの収集の構成を表すもの
    """
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
    
    PYTHON_MODULE_EXT = (
        "py",
        "pyd",
    )
    
    
    #region 相対ファイルパスから完全名を生成する
    def py_to_fullname(self, relfilename):
        if relfilename.namepart() == "__init__":
            # モジュールはファイル名を含めない
            # e.g path/to/module/__init__.py => path.to.module
            return relfilename.replaced(namepart = "", extpart = "", ensure_abspath = False).replace("/", ".")
        else:
            # e.g path/to/module/foo.py => path.to.module.foo
            return relfilename.replaced(extpart = "", ensure_abspath = False).replace("/", ".")
    
    def pyd_to_fullname(self, relfilename):
        # e.g path/to/module/foo.arc-version-sig.pyd => path.to.module.foo
        modname = relfilename.basename().split(".")[0]
        pkgname = relfilename.dirname().replace("/", ".")
        return (pkgname + "." + modname) if pkgname else modname
    #endregion 相対ファイルパスから完全名を生成する
    
    def dump_to(self, dumpobj):
        zipsafe = utils.PathMatcher(*self.zipsafe)
        for ent in self.iter_files():
            assert isinstance(ent, utils.FilePath)
            relfilename = ent.relpath(self.root)
            fullname_converter = getattr(self, "%s_to_fullname" % relfilename.extpart(), None)
            fullname = None if not fullname_converter else fullname_converter(relfilename)
            dumpobj.write_python(
                ent,
                relfilename,
                fullname = fullname,
                zipsafe = zipsafe(ent),
            )

@PackagesConfiguration.register("python-base")
class PythonBasePackageConfig(PythonPackingConfiguration):
    """
    Pythonモジュールの site-packages以外のモジュールの収集の構成を表すもの
    """
    class Default(PythonPackingConfiguration.Default):
        pass

@PackagesConfiguration.register("site-packages")
class PythonSitePackageConfig(PythonPackingConfiguration):
    """
    Pythonモジュールの site-packagesのモジュールの収集の構成を表すもの
    """
    class Default(PythonPackingConfiguration.Default):
        pass

@PackagesConfiguration.register("depends")
class DependentPackageConfig(PackingConfigration):
    """
    依存ファイル(ネイティブライブラリやテキストコンテンツなど)の収集の構成を表すもの
    """
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

class AbstractResourceComposer(utils.Object):
    """
    :func:`SiteConfiguration.dump` で、Pythonモジュール、Python拡張モジュール、依存ファイルを適切に格納するストレージを表すもの
    
    :var siteconf: 格納中の :class:`SiteConfiguration` インスタンス
    :var dist: このストレージを通して格納された要素を保存する :class:`utils.Dict` 型のインスタンス
    
    * `dist` は以下の構造を持つ
    
        {
            config: 初期化時に渡された siteconfの siteconf.outputs の値,
            files: {
                [string: 格納されたファイルの格納時の相対パス]: [
                    string: Pythonモジュールの fullname(格納されたファイルが Pythonモジュールの場合のみ),
                    bool: ファイルがコンテナ内コンテナとして格納されていることを示す値,
                ]
            },
            expand_dir: 展開時にコンテナ内コンテナ以外のファイルが展開される先の相対パス
        }
    
    """
    siteconf = None
    dist = None
    
    def __init__(self, siteconf, **options):
        utils.Object.__init__(self, **options)
        assert isinstance(siteconf, SiteConfiguration)
        assert siteconf.outputs, "`outputs` is not configured: siteconf.outputs=%s" % siteconf.outputs
        siteconf.outputs.configured()
        self.siteconf = siteconf
        self.dist = utils.Dict(
            config = siteconf.outputs,
            files = utils.Dict(), # module, extmodules問わず
            expand_dir = siteconf.outputs.distname + ".exp",
            composer = self.cls.__name__,
        )
    
    def add_distinfo(self, stored_filename, python_mod_fullname = None, zipsafe = False):
        self.dist.files[stored_filename] = (python_mod_fullname, bool(zipsafe))
    
    def write_python(self, filename, modpath, fullname = None, zipsafe = True):
        raise NotImplementedError("abstract")
    
    def write_depends(self, filename, arcname):
        raise NotImplementedError("abstract")
    
    def close(self):
        raise NotImplementedError("abstract")
    
    def __enter__(self):
        return self
    
    def __exit__(self, etype, einst, etrace):
        self.close()

class ZipResourceComposer(AbstractResourceComposer):
    """
    このストレージは :func:`~write_python` で Pythonのローダで読み込み可能なモジュールを「Pythonモジュール」として ZIP-in-ZIPとして格納し、
    :func:`~write_depends` で Pythonのローダで読み込めない依存コンテンツを ZIP内ファイルとして格納する。
    wip
    """
    def __init__(self, siteconf, **options):
        AbstractResourceComposer.__init__(self, siteconf, **options)
        self.modules = utils.ZipOutput(compress = zipfile.ZIP_STORED)
        self.outputfilename = utils.FilePath.ensure(self.siteconf.outputs.filename).abspath()
        self.outputfilename.dirname().touch()
        self.zout = utils.ZipOutput(self.outputfilename, zipfile.ZIP_DEFLATED)
        self.__closed = False
    
    def write_python(self, filename, modpath, fullname = None, zipsafe = True):
        """
        このストレージへ Pythonモジュールを格納する
        
        `fullname` は、 `filename` およびそれが表す `modpath` がPythonモジュールである場合にのみ、
        そのモジュールの完全名(dotted)を与えなければならない
        """
        zipsafe = bool(zipsafe)
        self.add_distinfo(modpath, fullname, zipsafe)
        if zipsafe:
            print("DumpObject.write_python %s -> %s(%s, %s)" % (filename, modpath, fullname, zipsafe))
            self.modules.writefile(filename, modpath)
        else:
            modpath = self.dist.expand_dir + "/" + modpath
            print("DumpObject.write_python %s -> %s(%s, %s)" % (filename, modpath, fullname, zipsafe))
            self.zout.writefile(filename, modpath)
    
    def write_depends(self, filename, arcname):
        """
        このストレージへ依存ファイルを格納する
        """
        arcname = self.dist.expand_dir + "/" + arcname
        print("DumpObject.write_depends%s -> %s" % (filename, arcname))
        self.zout.writefile(filename, arcname)
    
    def close(self):
        """
        このストレージへの格納を完了し、AMPのパッケージファイルを生成する
        """
        if self.__closed:
            return
        self.__closed = True
        with self.modules.finishing() as modules:
            print("Adding %s" % self.siteconf.outputs.modules)
            self.zout.writefile(modules.filename, self.siteconf.outputs.modules)
            print("Adding %s" % self.siteconf.outputs.distname)
            with self.zout.open(self.siteconf.outputs.distname, "w") as fp:
                fp.write(utils.short_json_encoder.encode(self.dist))
            
            with self.zout.open("bootstrap.py", "wb") as fp:
                src = template_bootstrap.BOOTSTRAP_PY.format(**self.siteconf.outputs)
                fp.write(utils.ensure_bytes(src))
            with self.zout.open("winpshell.bat", "wb") as fp:
                src = template_bootstrap.PSHELL_BAT.format(
                    python_executable = "python.exe",
                    bootstrap_py_name = "bootstrap.py",
                    **self.siteconf.outputs
                )
                fp.write(utils.ensure_bytes(src))
        self.zout.close()
        print("Finish %s" % self.siteconf.outputs.filename)

class BlobStoreResourceComposer(ZipResourceComposer):
    """
    このストレージは :func:`~write_python` で Pythonのローダで読み込み可能なモジュールを「Pythonモジュール」として Blob-in-ZIPとして格納し、
    :func:`~write_depends` で Pythonのローダで読み込めない依存コンテンツを ZIP内ファイルとして格納する。
    (agonist of DumpObject)
    """
    def __init__(self, siteconf, **options):
        ZipResourceComposer.__init__(self, siteconf, **options)
        self.modules = utils.WrappedBlobWriter()
