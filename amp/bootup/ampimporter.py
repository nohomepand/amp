#!/usr/bin/env python
# encoding: utf-8
"""
Created on 2020/04

@author: nonamepand

* Python Module Finder/Loader implementation for AMP; see also PEP-302, and PEP-451
 - related Python's documentation
  - (py3k): https://docs.python.org/3/library/importlib.html
* NOTE; this module and enclosing packages should be installed as `plain` files
"""
from __future__ import absolute_import, print_function

import sys
from . import blobstore
try:
    import _frozen_importlib as frozen_importlib # noqa
except ImportError:
    frozen_importlib = None
ModuleType = type(sys)

#region os.path operations, and utilities
_builtin_names = sys.builtin_module_names

if 'posix' in _builtin_names:
    # For Linux, Unix, Mac OS X
    def is_abspath(s):
        # returns whether the target `s` points to absolute file path
        if not s: return False
        return s[0] in ("/", "\\")
    os_seps = ("/", ) #: path separators
elif 'nt' in _builtin_names:
    # For Windows
    def is_abspath(s):
        # returns whether the target `s` points to absolute file path
        if not s: return False
        return len(s) >= 2 and ("a" <= s[0] <= "z" or "A" <= s[0] <= "Z") and s[1] == ":"
    os_seps = ("/", "\\") #: path separators
else:
    raise RuntimeError("Unknown platform")

def norm_path(path, chars = ("\\", ), sep = "/"):
    """
    normalizes Path string from `chars` into `sep` string
    """
    for ch in chars:
        path = path.replace(ch, sep)
    return path

def os_path_join(*args, **kw):
    """
    :func:`os.path.join` shim;
    this function can be concatenate relative paths (and also absolute one) into a single path string.
    
    see also PyInstaller::https://github.com/pyinstaller/pyinstaller/blob/develop/PyInstaller/loader/pyimod01_os_path.py
    
    .. code-block::
    
        os_path_join("foo", "bar", "baz") # foo/bar/baz
        os_path_join("foo", "bar/baz") # foo/bar/baz
        os_path_join("foo", "/bar", "baz") # /bar/baz (NOTE; this behaviour is only in `posix` env.)
    """
    sep = kw.get("sep", "/")
    seps = (os_seps + (sep, )) if not sep in os_seps else os_seps
    def _join(a, *args):
        if not a: # e.g `a == ""`
            return _join(*args)
        else:
            if a[-1] in seps:
                a = a[:-1]
            if not args:
                return a
            b, args = args[0], args[1:]
            if is_abspath(b):
                # `b` points to absolute path
                return _join(b, *args)
            else:
                return a + sep + _join(b, *args)
    return _join(*args) if args else ""

def os_path_dirname(path, **kw):
    """
    :func:`os.path.dirname` shim;
    """
    sep = kw.get("sep", "/")
    seps = (os_seps + (sep, )) if not sep in os_seps else os_seps
    ps = max([path.rfind(s) for s in seps])
    if ps < 0:
        return "" # no dirname
    else:
        return path[:ps]

class MixinFunc(object):
    """
    Mixin-able object interface
    
    .. code-block::
    
        class Mix1(MixinFunc):
            def method1(self):
                raise NotImplementedError()
        
        class Obj2(Mix1):
            def method1(self):
                return "foo"
        
        class Obj2(Mix1):
            pass
        
        Mix1.check_is_like(Obj1()) # pass
        Mix1.check_is_like(Obj2()) # error
    """
    @classmethod
    def is_not_like(cls, that):
        """
        return False-like values when `that` object has all of members in this class
        """
        missing_attrs = []
        for c in cls.mro():
            for k in c.__dict__:
                if k[0] == "_":
                    continue
                v = c.__dict__[k]
                if isinstance(v, classmethod):
                    continue
                if not hasattr(that, k):
                    missing_attrs.append(k)
        return missing_attrs
    
    @classmethod
    def check_is_like(cls, that):
        """
        (assertion test)
        """
        missings = cls.is_not_like(that)
        assert not missings, "Missing some attributes in %s: require %s" % (that, missings)
    
#endregion os.path operations, and utilities

#region abstract module finder/loaders
class AbstractFinder(object):
    """
    PEP-302 (partial PEP-451) module finder interfaces
    """
    def find_module(self, fullname, path=None):
        # Deprecated in Python 3.4, see PEP-451
        """
        PEP-302 finder.find_module() method for the ``sys.meta_path`` hook.
        fullname     fully qualified name of the module
        path         None for a top-level module, or package.__path__
                     for submodules or subpackages.
        Return a loader object if the module was found, or None if it wasn't.
        If find_module() raises an exception, it will be propagated to the
        caller, aborting the import.
        """
        return None

class AbstractLoader(object):
    """
    PEP-302 (partial PEP-451) module loader interfaces
    """
    
    def load_module(self, fullname, entry_name=None, *args):
        # Deprecated in Python 3.4, see PEP-451
        """
        PEP-302 loader.load_module() method for the ``sys.meta_path`` hook.
        Return the loaded module (instance of imp_new_module()) or raises
        an exception, preferably ImportError if an existing exception
        is not being propagated.
        When called from FrozenPackageImporter, `entry_name` is the name of the
        module as it is stored in the archive. This module will be loaded and installed
        into sys.modules using `fullname` as its name
        """
    
    #region optional PEP-302
    def get_filename(self, fullname):
        """
        This method should return the value that __file__ would be set to
        if the named module was loaded. If the module is not found, then
        ImportError should be raised.
        """
        raise ImportError(fullname)
    
    def is_package(self, fullname):
        """
        An abstract method to return a true value if the module is a package,
        a false value otherwise. ImportError is raised if the loader cannot
        find the module.
        Changed in version 3.4: Raises ImportError instead of NotImplementedError.
        """
        raise ImportError(fullname)
    
    def get_code(self, fullname):
        """
        Get the code object associated with the module.
        ImportError should be raised if module not found.
        """
        raise ImportError(fullname)
    
    def get_source(self, fullname):
        """
        Method should return the source code for the module as a string.
        But frozen modules does not contain source code.
        Return None.
        """
        return None
    
    def get_data(self, path):
        """
        This returns the data as a string, or raise IOError if the "file"
        wasn't found. The data is always returned as if "binary" mode was used.
        This method is useful getting resources with 'pkg_resources' that are
        bundled with Python modules in the PYZ archive.
        The 'path' argument is a path that can be constructed by munging
        module.__file__ (or pkg.__path__ items)
        """
        """
        An abstract method to return the bytes for the data located at path.
        Loaders that have a file-like storage back-end that allows storing
        arbitrary data can implement this abstract method to give direct access
        to the data stored. OSError is to be raised if the path cannot be found.
        The path is expected to be constructed using a module’s __file__
        attribute or an item from a package’s __path__.
        
        Changed in version 3.4: Raises OSError instead of NotImplementedError.
        """
        raise IOError(path)
    #endregion optional PEP-302

class AbstractRelativeLoader(MixinFunc):
    """
    (interface)
    object which can set/clear `delegation file path`
    """
    def set_delegate_path(self, path):
        """
        set current delegation file path
        """
        raise NotImplementedError()
    
    def clear_delegate_path(self):
        """
        clear current delegation file path
        """
        raise NotImplementedError()
    
#endregion abstract module finder/loaders

#region AMP importer implementations
#region importer python path utils
class GetRelativePathMixin(MixinFunc):
    """
    (interface)
    object which has `basepath` and `relative path concatenation`;
    this mixin denotes an ability to compose and split paths which is originated to this object.
    """
    
    def get_basepath(self):
        """
        returns base path string
        """
        raise NotImplementedError()
    
    def get_relpath(self, path):
        """
        make `relative path` from target (absolute) paths based on :func:`self.get_basepath`.
        """
        raise NotImplementedError()

class PythonPath(str):
    """
    string derived object which denotes a path of Python Module on corresponding loader object;
    this object also has `is_package` and `package_path` attributes.
    
    :data:`~is_package` is True if this object point to Python package.
    :data:`~package_path` is a PythonPath derived instance which is a path to package of this instance.
    """
    def __new__(cls, filepathlike, fullname):
        """
        (for instantiation hook)
        create new instance
        
        :param filepathlike: Python module/package path
        :param fullname: Python module/packages' fullname
        """
        return str.__new__(cls, filepathlike)
    
    is_package = None
    package_path = None
    
    def __init__(self, _, fullname):
        self.fullname = fullname

class PythonModulePath(PythonPath):
    """
    Python module path string.
    """
    is_package = property(lambda self: False)
    
    def __init__(self, filepathlike, fullname):
        PythonPath.__init__(self, _, fullname)
        package_name = fullname.rsplit(".", 1)[0]
        self.package_path = PythonPackagePath(
            os_path_join(os_path_dirname(filepathlike), "__init__.py"),
            package_name
        )

class PythonPackagePath(PythonPath):
    """
    Python package path string.
    """
    is_package = property(lambda self: True)
    package_path = property(lambda self: self)
#endregion importer python path utils

class AMPStackedFinder(AbstractFinder):
    """
    unionfsのように積層的に登録されたローダを通じてロードする代表のファインダ;
    モジュールの検索パスはただ一つのルートを持つように変更される
    """
    
    def __init__(self, delegation_path):
        """
        初期化
        
        :param delegation_path: このファインダからロードされたモジュールの基底のパス
        """
        self.delegation_path = delegation_path
        self.__importers = []
    
    def register(self, importer):
        """
        モジュールローダを登録する;
        登録されたモジュールローダは常に「最後に検索される」ように扱われる
        """
        GetRelativePathMixin.check_is_like(importer)
        AbstractRelativeLoader.check_is_like(importer)
        self.unregister(importer)
        self.__importers.append(importer)
        importer.set_delegate_path(self.delegation_path)
        return importer
    
    def unregister(self, importer):
        """
        モジュールローダの登録を解除する
        """
        if importer in self.__importers:
            self.__importers.remove(importer)
            importer.clear_delegate_path()
            return importer
    
    @property
    def importers(self):
        """
        (immutable)
        登録されたモジュールローダの、検索順序に基づく整列されたタプルを得る
        """
        return tuple(self.__importers)
    
    def find_module(self, fullname, path=None):
        # override
        for importer in self.__importers:
            found = importer.find_module(fullname, path = path)
            if found:
                return selectable_loader(self, found) # TODO: cache?
    
    def synth_path(self, loader_relpath):
        """
        対象の相対パスを、このファインダの基底のパス以下のパスとして結合した値を得る;
        結合されたパスは実体が存在しない可能性があるが、モジュールの検索以外のパス操作(依存ファイルのパスの解決)などで、
        すべてのモジュールローダが連合したかのような操作を行うために必要。
        (ZIPに格納されたモジュールからの相対パスで依存ファイルを解決する場合など)
        """
        return os_path_join(self.delegation_path, loader_relpath)
    
    def related_path(self, synth_path):
        """
        対象の絶対パスを、このファインダの基底のパスからの相対パスとして分解した値を得る
        """
        assert synth_path.startswith(self.delegation_path)
        return synth_path[len(self.delegation_path):]

class selectable_loader(AbstractLoader):
    """
    (internal)
    :class:`AMPStackedFinder` の `find_module` で返却されるモジュールローダのプロキシとなるもの
    """
    def __init__(self, parent, loader_impl):
        assert isinstance(parent, AMPStackedFinder)
        GetRelativePathMixin.check_is_like(loader_impl)
        self.parent = parent
        self.loader = loader_impl
    
    def load_module(self, fullname, entry_name=None):
        # override
        """
        対象の Python完全名を :func:`self.loader.load_module` でロードした後に、
        ファイルパスを :data:`self.parent` の相対パスとして再構成したモジュールを返却する
        """
        try:
            return sys.modules[fullname]
        except LookupError:
            mod = self.loader.load_module(fullname, entry_name = entry_name) # may be raise ImportError
            mod.__file__ = self.parent.synth_path(self.loader.get_relpath(mod.__file__))
            mod.__loader__ = self
            if hasattr(mod, "__path__"):
                mod.__path__ = list(map(lambda path: self.parent.synth_path(self.loader.get_relpath(path)), mod.__path__))
            if getattr(mod, "__spec__", None):
                """
                self.name = name
                self.loader = loader
                self.origin = origin
                self.loader_state = loader_state
                self.submodule_search_locations = [] if is_package else None
                """
                mod.__spec__.loader = self
            
            sys.modules[fullname] = mod # override
            return mod
    
    def get_filename(self, fullname):
        s = self.loader.get_filename(fullname)
        return s.__class__(self.parent.synth_path(s), fullname)
    
    def is_package(self, fullname):
        return self.loader.get_filename(fullname).is_package
    
    def get_code(self, fullname):
        return self.loader.get_code(fullname)
    
    def get_source(self, fullname):
        return self.loader.get_source(fullname)
    
    def get_data(self, path):
        path = os_path_join(self.loader.get_basepath(), self.parent.related_path(path))
        return self.loader.get_data(path)

class AMPBlobStoreImporter(AbstractFinder, AbstractLoader):
    """
    :class:`blobstore.BlobReader` で読み取れるコンテナファイルからモジュールを検索/ロードするインポータ
    """
    def __init__(self, filename):
        self.br = blobstore.BlobReader(filename)
        self.__delegate_path = ""
    
    def set_delegate_path(self, path):
        self.__delegate_path = path
    
    def clear_delegate_path(self):
        self.__delegate_path = ""
    
    def find_module(self, fullname, path=None):
        try:
            self.get_filename(fullname) # test
            return self
        except ImportError:
            pass
    
    def get_basepath(self):
        return self.br.filename
    
    def get_relpath(self, path):
        if not path.startswith(self.br.filename): # FIXME: case-insensitive?
            return path
        return path[len(self.br.filename):]
    
    def load_module(self, fullname, entry_name=None):
        try:
            return sys.modules[fullname]
        except LookupError:
            pass
        # 標準のローダプロトコルに従って fullname モジュールを生成する
        pypath = self.get_rel_filename(fullname)
        module = ModuleType(fullname)
        module.__file__ = os_path_join(self.br.filename, pypath)
        if pypath.is_package:
            module.__path__ = [pypath.package_path]
            module.__package__ = fullname
        else:
            module.__package__ = pypath.package_path.fullname
        module.__loader__ = self
        if frozen_importlib:
            module.__spec__ = frozen_importlib.ModuleSpec(
                fullname,
                self,
                is_package = pypath.is_package,
            )
        sys.modules[fullname] = module
        contents = self.br.read(pypath)
        try:
            exec(self.get_code(fullname), module.__dict__)
            module = sys.modules[fullname]
            return module
        except:
            sys.modules.pop(fullname, None)
            raise
    
    def get_rel_filename(self, fullname):
        s = fullname.replace(".", "/")
        if (s + ".py") in self.br.files:
            return PythonModulePath(s + ".py", fullname)
        elif (s + "/__init__.py") in self.br.files:
            return PythonPackagePath(s + "/__init__.py", fullname)
        else:
            raise ImportError(fullname)
    
    def get_filename(self, fullname):
        s = self.get_rel_filename(fullname)
        return s.__class__(os_path_join(self.__delegate_path, s), fullname)
    
    def is_package(self, fullname):
        return self.get_rel_filename(fullname).is_package
    
    def get_code(self, fullname):
        s = self.get_rel_filename(fullname)
        return compile(self.br.read(s), s.__class__(os_path_join(self.__delegate_path, s), fullname), "exec", dont_inherit=True)
    
    def get_source(self, fullname):
        return self.br.read(self.get_rel_filename(fullname))
    
    def get_data(self, path):
        return self.br.read(path)
#endregion AMP importer implementations
