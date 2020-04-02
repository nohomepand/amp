# encoding: utf-8
'''
Created on 2020/03/27

@author: oreyou
'''
from __future__ import absolute_import, print_function, unicode_literals

import sys

from amp.core import utils


#region Resources
class ResourceScanner(utils.Object):
    """
    
    :class:`utils.RelativeFile` を生成・列挙する機能を表すもの
    """
    includes = [
    ]
    excludes = [
    ]
    
    def __init__(self, **options):
        utils.Object.__init__(self, **options)
        self.includes = utils.PathMatcher(*self.includes)
        self.excludes = utils.PathMatcher(*self.excludes)
    
    def is_acceptable(self, path):
        return not (self.excludes(path) and not self.includes(path))
    
    def __iter__(self):
        """
        このローダに基づく :class:`utils.RelativeFile` を列挙する
        """
        raise NotImplementedError()

class Resource(utils.Object):
    
    filepath = None
    
    @property
    def arcname(self):
        raise NotImplementedError()

#region Resources - Python package
class PythonPackageResource(Resource):
    def __init__(self, package_dir, filepath, **options):
        Resource.__init__(self, **options)
        self.package_dir = package_dir
        self.filepath = filepath
    
    @property
    def is_zip_safe(self):
        return self.filepath.endswith(".py")
    
    @property
    def arcname(self):
        return self.filepath.relpath(self.package_dir)

class PythonPackageScanner(ResourceScanner):
    """
    Pythonのファイルシステム上のパッケージを列挙するもの;
    Pythonの基本的なパッケージと sites-packagesのパッケージ(sites.pyによって sys.pathに挿入される検索パス上のパッケージ)を走査する
    """
    includes = [
        #".*\\.py$",
        ".*\\.pyd$",
    ]
    excludes = [
        ".*\\.pyc$",
        ".*?/test(s?)/.*?",
    ]
    
    def __init__(self, sys_paths = None, **options):
        ResourceScanner.__init__(self, **options)
        self.sys_paths = sys.path if sys_paths is None else sys_paths
        self.targets = utils.Dict(
            bases = list(
                map(
                    utils.FilePath.ensure,
                    filter(lambda e: not "site-packages" in e, self.sys_paths)
                )
            ),
            sites = list(
                map(
                    utils.FilePath.ensure,
                    filter(lambda e: "site-packages" in e, self.sys_paths)
                )
            ),
        )
    
    def _iter_bases(self):
        """
        Pythonの site-packages以外のパッケージを走査する
        """
        for path in self.targets.bases:
            for entry in self._scan_package(path, False):
                yield PythonPackageResource(path, entry)
    
    def _iter_sites(self):
        """
        Pythonの site-packagesのパッケージを走査する
        """
        for path in self.targets.sites:
            for entry in self._scan_package(path, True):
                yield PythonPackageResource(path, entry)
    
    def _scan_package(self, path, sites_mode = False):
        """
        pathをsys.pathのパスとみなして、パッケージと関連ファイルを列挙する
        """
        assert isinstance(path, utils.FilePath)
        if path.isdir():
            # トップレベル要素は pyまたは */__init__.pyを含む1レベル要素
            for toplevel in path.list(False):
                if not self.is_acceptable(toplevel):
                    continue
                if not sites_mode and "site-packages" in toplevel:
                    continue
                if toplevel.isdir() and toplevel.join("__init__.py").isfile():
                    # 1レベル要素は全てのパッケージ
                    for entry in toplevel.list(True):
                        if not self.is_acceptable(entry):
                            continue
                        yield entry
                elif toplevel.isfile():
                    yield toplevel
        elif path.isfile():
            # may be zip file(for loading by zipimporter)
            if self.is_acceptable(path):
                yield path
    
    def __iter__(self):
        for ent in self._iter_bases():
            yield ent
        for ent in self._iter_sites():
            yield ent
#endregion Resources - Python package

#region Resources - Dependent file
class DependencyResource(Resource):
    def __init__(self, filepath, **options):
        Resource.__init__(self, **options)
        self.filepath = filepath
    
    @property
    def arcname(self):
        return self.filepath.basename()

class DependencyScanner(ResourceScanner):
    """
    環境変数 `PATH` などのPython外の検索パス直下のファイルを列挙する;
    単一のファイルであるか、またはサブディレクトリであるか、いずれも列挙される
    """
    includes = [
    ]
    
    excludes = [
    ]
    
    deep = False
    
    def __init__(self, root, **options):
        ResourceScanner.__init__(self, **options)
        self.root = utils.FilePath.ensure(root)
    
    def __iter__(self):
        if self.root.isdir():
            for entry in self.root.list(self.deep):
                if self.is_acceptable(entry):
                    yield DependencyResource(entry)
        elif self.root.isfile():
            if self.is_acceptable(self.root):
                yield DependencyResource(self.root)
#region Resources - Dependent file

#endregion Resources

if __name__ == '__main__':
    for ent in PythonPackageScanner():
        if isinstance(ent, PythonPackageResource):
            print(ent.is_zip_safe, ent.arcname)
