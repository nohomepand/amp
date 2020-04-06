#!/usr/bin/env python
# encoding: utf-8
"""

"""
from __future__ import absolute_import, print_function, unicode_literals

import sys
from . import blobstore

# import os

# def joinpath(*subpath, **kwargs):
#     return os.path.abspath(os.path.join(kwargs.get("basedir", joinpath.basedir), *subpath))
# joinpath.basedir = os.path.dirname(__file__)

# isdir = os.path.isdir
# isfile = os.path.isfile
# def checkfile(path, v = isfile):
#     assert v(path), "Not found {{path}}".format(**locals())
#     return path

ModuleType = type(sys)

_builtin_names = sys.builtin_module_names
if 'posix' in _builtin_names:  # For Linux, Unix, Mac OS X
    def is_abspath(s):
        if not s: return False
        return s[0] in ("/", "\\")
elif 'nt' in _builtin_names:  # For Windows
    def is_abspath(s):
        if not s: return False
        return len(s) >= 2 and ("a" <= s[0] <= "z" or "A" <= s[0] <= "Z") and s[1] == ":"
else:
    raise RuntimeError("Unknown platform")

def os_path_join(*args, **kw):
    # see also PyInstaller::https://github.com/pyinstaller/pyinstaller/blob/develop/PyInstaller/loader/pyimod01_os_path.py
    sep = kw.get("sep", "/")
    seps = ("/", "\\") + (sep, )
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

class AbstractFinder(object):
    """
    PEP-302(partial PEP-451) module finder implementation for AMP
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
    PEP-302(partial PEP-451) module loader implementation for AMP
    
    class Loader(metaclass=ABCMeta):
        def load_module(self, fullname: str) -> ModuleType: ...
        def module_repr(self, module: ModuleType) -> str: ...
        def create_module(self, spec: ModuleSpec) -> Optional[ModuleType]: ...
        # Not defined on the actual class for backwards-compatibility reasons,
        # but expected in new code.
        def exec_module(self, module: ModuleType) -> None: ...
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
    
    def is_package(self, fullname):
        return False
    
    def get_code(self, fullname):
        """
        Get the code object associated with the module.
        ImportError should be raised if module not found.
        """
    
    def get_source(self, fullname):
        """
        Method should return the source code for the module as a string.
        But frozen modules does not contain source code.
        Return None.
        """
    
    def get_data(self, path):
        """
        This returns the data as a string, or raise IOError if the "file"
        wasn't found. The data is always returned as if "binary" mode was used.
        This method is useful getting resources with 'pkg_resources' that are
        bundled with Python modules in the PYZ archive.
        The 'path' argument is a path that can be constructed by munging
        module.__file__ (or pkg.__path__ items)
        """
    #endregion optional PEP-302

class GetRelativePathMixin(object):
    def get_basepath(self):
        raise NotImplementedError()
    
    def get_relpath(self, path):
        raise NotImplementedError()
    
    @classmethod
    def is_relativepath_like(cls, that):
        for k in cls.__dict__:
            assert hasattr(that, k), "Require %s attribute in %s" % (k, that)
        return that

class PythonModulePath(str): pass
class PythonPackagePath(str): pass

class AMPStackedImporter(AbstractFinder, AbstractLoader):
    """
    unionfsのように積層的に登録されたローダを通じてロードする代表のローダ;
    ロードされたモジュールの検索パスはただ一つのルートを持つように変更される
    """
    
    def __init__(self, delegation_path):
        self.delegation_path = delegation_path
        self.__importers = []
    
    def register(self, importer):
        if importer in self.importers:
            self.__importers.remove(importer)
        assert GetRelativePathMixin.is_relativepath_like(importer)
        self.__importers.append(importer)
        return importer
    
    def unregister(self, importer):
        if importer in self.importers:
            self.__importers.remove(importer)
            return importer
    
    def find_module(self, fullname, path=None):
        for importer in self.__importers:
            found = importer.find_module(fullname, path = path)
            if found:
                if isinstance(found, tuple):
                    found, args = found[0], found[1:]
                else:
                    args = ()
                return selectable_loader(self, found, *args)
    
    def synth_path(self, loader_relpath):
        print("synth_path", loader_relpath)
        return os_path_join(self.delegation_path, loader_relpath)
    
    def related_path(self, synth_path):
        assert synth_path.startswith(self.delegation_path)
        return synth_path[len(self.delegation_path):]

class selectable_loader(AbstractLoader):
    def __init__(self, parent, loader_impl, *loader_args):
        assert isinstance(parent, AMPStackedImporter)
        assert GetRelativePathMixin.is_relativepath_like(loader_impl)
        self.parent = parent
        self.loader = loader_impl
        self.loader_args = loader_args
        self.get_filename = self.loader.get_filename
        self.is_package = getattr(self.loader, "is_package", lambda fullname: None)
        self.get_code = self.loader.get_code
        self.get_source = self.loader.get_source
    
    def load_module(self, fullname, entry_name=None):
        try:
            sys.modules[fullname]
        except LookupError:
            mod = self.loader_impl.load_module(fullname, entry_name = entry_name, *self.loader_args)
            if not mod:
                return
            """
            ('__cached__', None)
            ('__doc__', None)
            ('__file__', 'Z:\\out\\out\\py\\django\\__init__.py')
            ('__loader__', <zipimporter object "Z:\out\out\py">)
            ('__name__', 'django')
            ('__package__', 'django')
            ('__path__', ['Z:\\out\\out\\py\\django'])
            ('__spec__', ModuleSpec(name='django', loader=<zipimporter object "Z:\out\out\py">, origin='Z:\\out\\out\\py\\django\\__init__.py', submodule_search_locations=['Z:\\out\\out\\py\\django']))
            ('__version__', '2.0')
            ('get_version', <function get_version at 0x02DFE7C8>)
            ('setup', <function setup at 0x02E116F0>)
            ('utils', <module 'django.utils' from 'Z:\\out\\out\\py\\django\\utils\\__init__.py'>)

                if is_pkg:
                    module.__package__ = fullname
                else:
                    module.__package__ = fullname.rsplit('.', 1)[0]

            """
            mod.__file__ = self.parent.synth_path(self.loader.get_relpath(mod.__file__))
            mod.__loader__ = self
            if is_pkg:
                mod.__package__ = fullname
                mod.__path__ = list(map(lambda path: self.parent.synth_path(self.loader.get_relpath(path)), mod.__path__))
            else:
                mod.__package__ = fullname.rsplit('.', 1)[0]
            if hasattr(mod, "__spec__"):
                # PEP-451 ModuleSpec
                # see also importlib.machinery.ModuleSpec
                # TODO: wip
                mod.__spec__.loader = self
            return mod
    
    #region optional PEP-302
    def get_filename(self, fullname):
        # placeholder
        pass
    
    def is_package(self, fullname):
        # placeholder
        pass
    
    def get_code(self, fullname):
        # placeholder
        pass
    
    def get_source(self, fullname):
        """
        Method should return the source code for the module as a string.
        But frozen modules does not contain source code.
        Return None.
        """
    
    def get_data(self, path):
        """
        This returns the data as a string, or raise IOError if the "file"
        wasn't found. The data is always returned as if "binary" mode was used.
        This method is useful getting resources with 'pkg_resources' that are
        bundled with Python modules in the PYZ archive.
        The 'path' argument is a path that can be constructed by munging
        module.__file__ (or pkg.__path__ items)
        """
        path = os_path_join(self.loader.get_basepath(), self.parent.related_path(path))
        return self.loader.get_data(path)

class AMPBlobStoreImporter(AbstractFinder, AbstractLoader):
    def __init__(self, filename):
        self.br = blobstore.BlobReader(filename)
    
    def find_module(self, fullname, path=None):
        try:
            s = self.get_filename(fullname)
            return self, isinstance(s, PythonPackagePath) # is_package = True
        except ImportError:
            pass
    
    def get_basepath(self):
        return self.br.filename
    
    def get_relpath(self, path):
        pass
    
    def load_module(self, fullname, entry_name=None, is_package = None):
        try:
            return sys.modules[fullname]
        except LookupError:
            pass
        if is_package is None:
            filename = self.get_filename(fullname)
            is_package = isinstance(filename, PythonPackagePath)
            if is_package:
                package_path = fullname.replace(".", "/")
        elif is_package:
            package_path = fullname.replace(".", "/")
            filename = PythonPackagePath(package_path + "/__init__.py")
        else:
            filename = PythonPackagePath(fullname.replace(".", "/") + ".py")
        if not filename in self.br.files:
            raise ImportError(fullname)
        
        module = ModuleType(fullname)
        module.__file__ = self.br.filename + "/" + filename
        if is_package:
            module.__path__ = [package_path]
            module.__package__ = fullname
        else:
            module.__package__ = fullname.rsplit(".", 1)[0]
        module.__loader__ = self
        sys.modules[fullname] = module
        contents = self.br.read(filename)
        exec(contents, module.__dict__) # need compiled? / freezed module?
        module = sys.modules[fullname]
        return module
    
    #region optional PEP-302
    def get_filename(self, fullname):
        s = fullname.replace(".", "/")
        if (s + ".py") in self.br.files:
            is_package = False
            return PythonModulePath(s + ".py")
        elif (s + "/__init__.py") in self.br.files:
            return PythonPackagePath(s + "/__init__.py")
        else:
            raise ImportError(fullname)
    
    def is_package(self, fullname):
        return isinstance(self.get_filename(fullname), PythonPackagePath)
    
    def get_code(self, fullname):
        # placeholder
        filename = self.get_filename(fullname)
        return compile(self.br.read(filename), filename, "exec")
    
    def get_source(self, fullname):
        filename = self.get_filename(fullname)
        return self.br.read(filename)
    
    def get_data(self, path):
        """
        This returns the data as a string, or raise IOError if the "file"
        wasn't found. The data is always returned as if "binary" mode was used.
        This method is useful getting resources with 'pkg_resources' that are
        bundled with Python modules in the PYZ archive.
        The 'path' argument is a path that can be constructed by munging
        module.__file__ (or pkg.__path__ items)
        """
        return self.br.read(path)
