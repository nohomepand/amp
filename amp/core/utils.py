# encoding: utf-8
'''
Created on 2020/03/27

@author: oreyou
'''
from __future__ import absolute_import, print_function, unicode_literals

import functools
import inspect
import os
import re
import sys
import copy
import zipfile
import tempfile
import contextlib
import codecs


PY2 = sys.version_info.major == 2

class Object(object):
    def __init__(self, **options):
        self.__dict__.update(options)
    
    cls = property(lambda self: self.__class__)
    
    attrs = property(lambda self: sorted(vars(self).items(), key = lambda e: e[0]))
    
    def __str__(self):
        s = ", ".join(map(lambda kv: "%s=%r" % kv, self.attrs))
        return "{self.cls.__name__}({s})".format(**locals())

class Dict(dict):
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        else:
            return self.get(name, None)
    
    def __setattr__(self, name, value):
        if name in self:
            self[name] = value
        else:
            self.__dict__[name] = value
    
    def __delattr__(self, name):
        dict.__delattr__(self, name)
        self.pop(name, None)
    
    def __copy__(self):
        return self.__class__(self)

class AutoDict(Dict):
    class Default:
        pass
    
    def __init__(self, *args, **kwargs):
        for k in dir(self.Default):
            if k[0] == "_":
                continue
            v = getattr(self.Default, k)
            if callable(v):
                continue
            self[k] = copy.copy(v)
        Dict.__init__(self, *args, **kwargs)
    
    __components = None
    
    @classmethod
    def components(cls):
        if cls.__components is None:
            cls.__components = {}
        return cls.__components
    
    @classmethod
    def register(cls, typename):
        def wrapper(target):
            assert issubclass(target, AutoDict)
            target.Default.type = typename
            cls.components()[typename] = target
            return target
        return wrapper
    
    @classmethod
    def mount(cls, root, strict = False):
        if isinstance(root, (list, tuple)):
            d = []
            for ent in root:
                try:
                    typename = ent["type"]
                    subconf = cls.components().get(typename, None)
                    assert subconf, "No such type %r in %s of %r" % (typename, cls.components().keys(), cls)
                    d.append(subconf.mount(ent, strict))
                except LookupError:
                    if strict:
                        raise
                    d.append(cls.mount(ent, strict))
            return d
        else:
            d = {}
            for k, v in root.items():
                subconf = cls.components().get(k, None)
                if subconf:
                    v = subconf.mount(v, strict)
                d[k] = v
            return cls(**d)

def open_or(default = sys.stdout, output = None, file_mode = "wb", **file_kwargs):
    if not output:
        return default
    else:
        return open(output, file_mode, **file_kwargs)

if PY2:
    import cStringIO  # @NoMove
    StringIO = cStringIO.StringIO
    string_types = (basestring, )
    text_type = unicode
    str_type = bytes_type = str
    def ensure_str(a, encoding = "utf-8", errors = "ignore"):
        if isinstance(a, text_type):
            return a.encode(encoding, errors)
        elif not isinstance(a, bytes_type):
            return bytes_type(a)
        else:
            return a
else:
    import io  # @NoMove
    StringIO = io.StringIO
    string_types = (str, )
    str_type = text_type = str
    bytes_type = bytes
    def ensure_str(a, encoding = "utf-8", errors = "ignore"):
        if isinstance(a, bytes_type):
            return a.decode(encoding, errors)
        elif not isinstance(a, text_type):
            return text_type(a)
        else:
            return a
def ensure_bytes(a, encoding = "utf-8", errors = "strict"):
    if isinstance(a, text_type):
        return a.encode(encoding, errors)
    elif not isinstance(a, bytes_type):
        return bytes_type(a)
    else:
        return a

def ensure_text(a, encoding = "utf-8", errors = "ignore"):
    if isinstance(a, bytes_type):
        return a.decode(encoding, errors)
    elif not isinstance(a, text_type):
        return text_type(a)
    else:
        return a
stdout_encoding = getattr(sys.stdout, "encoding", None) or sys.getdefaultencoding()
ensure_stdout_str = functools.partial(ensure_str, encoding = stdout_encoding)
fsencoding = sys.getfilesystemencoding()
ensure_fsencoding_str = functools.partial(ensure_str, encoding = fsencoding)
ensure_fsencoding_text = functools.partial(ensure_text, encoding = fsencoding)

def printf(msg, *args, **kwargs):
    f = inspect.currentframe().f_back
    kwargs.update(f.f_globals)
    kwargs.update(f.f_locals)
    print(msg.format(*args, **kwargs))

class PathMatcher(Object):
    regex_flags = re.DOTALL
    def __init__(self, *patterns, **options):
        Object.__init__(self, **options)
        self.patterns = [
            re.compile(a, self.regex_flags) if isinstance(a, string_types) else a
            for a in patterns
        ]
    
    def __str__(self):
        s = tuple(map((lambda pat: pat.pattern), self.patterns))
        return "{self.__class__.__name__}({s})".format(**locals())
    
    __repr__ = __str__
    
    def __call__(self, path):
        for a in self.patterns:
            m = a.match(path)
            if m:
                return m
        return None

class FilePath(text_type):
    encoding = sys.getfilesystemencoding()
    errors = "strict"
    
    def __new__(cls, *args, **kwargs):
        path = os.path.join(*map(ensure_fsencoding_text, args))
        if os.sep != "/":
            path = path.replace(os.sep, "/")
        return text_type.__new__(cls, path)
    
    def __init__(self, *_, **options):
        self.__dict__.update(options)
    
    cls = property(lambda self: self.__class__)
    
    @classmethod
    def ensure(cls, it, **options):
        return it if isinstance(it, cls) else cls(it, **options)
    
    def isfile(self):
        return os.path.isfile(self)
    
    def isdir(self):
        return os.path.isdir(self)
    
    def touch(self, isdir = True):
        if isdir:
            if not self.isdir():
                os.makedirs(self.fsstr)
        elif not self.isfile():
            open(self, "wb").close()
    
    def exists(self):
        return os.path.exists(self)
    
    def to_fsstr(self):
        if PY2:
            return self.encode(fsencoding, self.errors)
        else:
            return text_type(self) # casting only
    
    fsstr = property(to_fsstr)
    
    def to_text(self):
        return text_type(self) # casting only
    
    text = property(to_text)
    
    def abspath(self, user = True, env = True):
        s = self.fsstr
        if user: s = os.path.expanduser(s)
        if env: s = os.path.expandvars(s)
        s = os.path.abspath(s)
        return self.cls(s, **self.__dict__)
    
    def relpath(self, start):
        if not isinstance(start, self.cls):
            start = self.cls(start, **self.__dict__)
        return self.cls(os.path.relpath(self.fsstr, start.fsstr), **self.__dict__)
    
    def basename(self):
        return self.cls(os.path.basename(self.fsstr), **self.__dict__)
    
    def dirname(self):
        return self.cls(os.path.dirname(self.fsstr), **self.__dict__)
    
    def join(self, *subpath):
        return self.cls(self, *subpath, **self.__dict__)
    
    def list(self, recursive_check = (lambda adir, depth = 0: False), depth = 0):
        recursive_check = recursive_check if callable(recursive_check) else (lambda *_, **__: bool(recursive_check))
        try:
            lsdir = os.listdir(self.fsstr)
        except OSError:
            lsdir = []
        for f in lsdir:
            np = self.join(f)
            yield np
            if np.isdir() and recursive_check(np, depth):
                for sub in np.list(recursive_check, depth = depth + 1):
                    yield sub
    
    def read(self, encoding = None, errors = None):
        if encoding:
            return codecs.open(self, "rU", encoding, errors).read()
        else:
            return open(self, "rb").read()

class ZipOutput(object):
    def __init__(self, zipfilename = None, compress = zipfile.ZIP_DEFLATED):
        self.__z = zipfile.ZipFile(zipfilename or tempfile.NamedTemporaryFile("wb", delete = False), "w", compress, True)
        self.filename = self.__z.filename
        self.packed = set()
    
    @property
    def raw_zipfile(self):
        return self.__z
    
    def close(self):
        if not self.__z:
            return
        self.__z.close()
        self.__z = None
    
    @contextlib.contextmanager
    def closing(self):
        self.close()
        yield self
        print("(remove tempfile %s)" % self.filename)
        os.remove(self.filename)
    
    def __enter__(self):
        return self
    
    def __exit__(self, etype, einst, etrace):
        self.close()
    
    def writefile(self, srcfile, arcname = None):
        if arcname is None:
            os.path.basename(srcfile)
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__z.write(srcfile, arcname)
    
    def writebytes(self, arcname, abytes = b""):
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__z.writestr(arcname, ensure_bytes(abytes))
    
    def writetext(self, arcname, texts = "", encoding = "utf-8", errors = "strict"):
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__z.writestr(arcname, ensure_bytes(texts, encoding, errors))
    
    @contextlib.contextmanager
    def open(self, arcname, mode = "wb"):
        with tempfile.NamedTemporaryFile(mode, delete = False) as tempf:
            yield tempf
            tempf.close()
            if not arcname in self.packed:
                self.packed.add(arcname)
                self.__z.write(tempf.name, arcname)
            os.remove(tempf.name)
