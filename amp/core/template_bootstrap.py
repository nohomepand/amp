# encoding: utf-8
'''
Created on date

@author: oreyou

* AMPの展開先用の起動スクリプトのテンプレート群
'''
from __future__ import unicode_literals, absolute_import, print_function

BOOTSTRAP_PY = """\
#!/usr/bin/env python
# encoding: utf-8
from __future__ import absolute_import, unicode_literals, print_function
import sys
import os


def joinpath(*subpath, **kwargs):
    return os.path.abspath(os.path.join(kwargs.get("basedir", joinpath.basedir), *subpath))
joinpath.basedir = os.path.dirname(__file__)

isdir = os.path.isdir
isfile = os.path.isfile
def checkfile(path, v = isfile):
    assert v(path), "Not found {{path}}".format(**locals())
    return path

def startup():
    DISTRIBUTION_CONTAINER = checkfile(joinpath("{distname}"))
    import json  # @NoMove
    DISTRIBUTION = json.loads(open(DISTRIBUTION_CONTAINER, "r").read())
    
    PYMODULE_CONTAINER = checkfile(joinpath("{{modules}}".format(**DISTRIBUTION["config"])))
    
    EXPAND_DIR = joinpath(DISTRIBUTION["expand_dir"])
    # require_update = bool(os.environ.get("AMP_REQUIRE_UPDATE", ""))
    #  if not isdir(EXPAND_DIR):
    #      os.makedirs(EXPAND_DIR)
    #      require_update = True
    #  
    checkfile(EXPAND_DIR, isdir)
    
    def unique_list_add(alist, *entries):
        for ent in entries:
            if not ent in alist:
                alist.append(ent)
        return alist
    os.environ["PATH"] = os.pathsep.join(unique_list_add(os.environ["PATH"].split(os.pathsep), EXPAND_DIR))
    unique_list_add(sys.path, PYMODULE_CONTAINER, EXPAND_DIR)
    
    import imp
    class BehalfImporter(object):
        RAW_IMPORTER_MAP = {{
            ".py": imp.load_source,
            ".pyd": imp.load_dynamic,
            ".dll": imp.load_dynamic,
            ".so": imp.load_dynamic,
        }}
        
        def __init__(
                self,
                import_base_dir = None,
                local_hooks = None,
            ):
            self.import_base_dir = import_base_dir or EXPAND_DIR
            self.local_hooks = local_hooks
        
        def __eq__(self, value):
            return isinstance(value, self.__class__) and self.import_base_dir == value.import_base_dir
        
        def find_module(self, fullname, path = None):
            namepart = joinpath(fullname.replace(".", "/"), basedir = self.import_base_dir)
            for ext in self.RAW_IMPORTER_MAP:
                if os.path.isfile(namepart + ext):
                    namepart += ext
                    if self.local_hooks:
                        trying = self.local_hooks.find_module(self, fullname, path, namepart)
                        if trying:
                            return trying
                    else:
                        return self
        
        def load_module(self, fullname):
            namepart = joinpath(fullname.replace(".", "/"), basedir = self.import_base_dir)
            for ext, rawimp in self.RAW_IMPORTER_MAP.items():
                if os.path.isfile(namepart + ext):
                    namepart += ext
                    if self.local_hooks:
                        trying = self.local_hooks.load_module(self, fullname, namepart, rawimp)
                        if trying:
                            return trying
                    else:
                        return rawimp(fullname, namepart)
    
    unique_list_add(sys.meta_path, BehalfImporter())
    
    return locals()

startup()
if __name__ == '__main__':
    def _():
        print(" sys.path ".center(20, "="))
        for el in sys.path:
            print(el)
        print("".center(20, "="))
    _()
"""

PSHELL_BAT = """\
@echo off
:pseudo python shell
setlocal
set EXPAND_DIR=.\\{distname}.exp
set PATH=%EXPAND_DIR%;%PATH%
set PYTHONPATH=.\\{modules}
set PYTHON={python_executable}
set BOOTMOD={bootstrap_py_name}
set PYTHONSTARTUP=%BOOTMOD%
%PYTHON%
endlocal
"""
