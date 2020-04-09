# encoding: utf-8
'''
Created on 2020/03/27

@author: oreyou

* AMPのユーティリティ関数群
'''
from __future__ import absolute_import, print_function, unicode_literals

import codecs
import contextlib
import copy
import functools
import inspect
import json
import os
import re
import sys
import tempfile
import zipfile
from amp.bootup import blobstore

PY2 = sys.version_info.major == 2

class Dict(dict):
    """
    プロパティアクセス可能な dict-like なオブジェクトを表すもの
    """
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
    """
    デフォルトの辞書エントリを持つ `Dict` クラス;
    デフォルトの辞書エントリの値は :func:`copy.copy` によって浅いコピーが行われる。
    TODO: components, register についての説明
    """
    class Default:
        """
        この `AutoDict` のデフォルトの辞書エントリ;
        `AutoDict` のサブクラスは、自身の `Default` に必要なデフォルトの辞書エントリを記述する。
        辞書キーは "_" で始まるもの、またはその辞書値が呼び出し可能なものは無視される
        """
    
    def __init__(self, *args, **kwargs):
        """
        デフォルトの辞書エントリで初期化した後に、与えられた引数で dictとして初期化する。
        """
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
        """
        この辞書の要素となりえる `AutoDict` のサブクラスの一覧を得る
        """
        if cls.__components is None:
            cls.__components = {}
        return cls.__components
    
    @classmethod
    def register(cls, typename):
        """
        この辞書の要素となりえる `AutoDict` のサブクラスを追加する
        """
        def wrapper(target):
            assert issubclass(target, AutoDict)
            target.Default.type = typename
            cls.components()[typename] = target
            return target
        return wrapper
    
    @classmethod
    def mount(cls, root, strict = False):
        """
        対象のオブジェクトの要素について、このクラスに `register` されたサブクラスとなるようにインスタンス化する。
        """
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
    """
    ファイルとして `output` を開くか、または `default` を返却する
    """
    if not output:
        return default
    else:
        return open(output, file_mode, **file_kwargs)

default_json_encoder = json.JSONEncoder(sort_keys=True, indent=2, separators=(',', ':'))
short_json_encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'))

#region Py2k Py3k compat. type&functions
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
#endregion Py2k Py3k compat. type&functions

def ellipse_str(it, length = 500, ellipsis = " .... ", to_str = repr):
    s = to_str(it)
    if len(s) > length:
        hl = int((length - len(ellipsis)) / 2)
        return s[:hl] + ellipsis + s[-hl:]
    else:
        return s

class Object(object):
    """
    コンストラクタ引数でプロパティを更新可能な `object` の基底の型
    """
    
    def __init__(self, **options):
        self.__dict__.update(options)
    
    cls = property(lambda self: self.__class__) #: shorthand property `self.__class__`
    
    attrs = property(lambda self: sorted(vars(self).items(), key = lambda e: e[0])) #: returns list of attrobite key-value tuple
    
    def __str__(self):
        s = ", ".join(map(lambda kv: "%s=%s" % (kv[0], ellipse_str(kv[1])), self.attrs))
        return "{self.cls.__name__}({s})".format(**locals())
    __repr__ = __str__

class PathMatcher(Object):
    """
    正規表現ベースのファイルパス検証用のオブジェクト
    """
    
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
        """
        このオブジェクトの :data:`self.patterns` のいずれかにマッチングするかを検証する
        """
        for a in self.patterns:
            m = a.match(path)
            if m:
                return m
        return None

class FilePath(text_type):
    """
    ファイルパスを表すもの;
    Pythonの文字列型を基底としていて、それらの機能に加えてファイル・コンテンツについての操作を含む。
    パスのセパレータは環境によらず "/" で連結される。
    
    .. code-block::
    
        p = FilePath(".")
        print(p) # "."
        print(p.join("foo", "bar")) # "./foo/bar"
        print(p.isfile()) # True/False; same to os.path.isfile(p)
        print(p.isdir()) # True/False; same to os.path.isdir(p)
        print(p.abspath()) # os.path.abspath(p)
    """
    errors = "strict"
    
    def __new__(cls, *args, **kwargs):
        """
        ポジショナル引数を os.path.join でファイルパスとして連結した形で初期化する
        """
        path = os.path.join(*map(ensure_fsencoding_text, args))
        if os.sep != "/":
            path = path.replace(os.sep, "/")
        return text_type.__new__(cls, path)
    
    def __init__(self, *_, **options):
        self.__dict__.update(options)
    
    cls = property(lambda self: self.__class__)
    
    @classmethod
    def ensure(cls, it, **options):
        """
        与えられたオブジェクトを `FilePath` へキャストする
        """
        return it if isinstance(it, cls) else cls(it, **options)
    
    def isfile(self):
        """
        このパスが示すファイルが通常のファイルであるか検証する
        """
        return os.path.isfile(self)
    
    def isdir(self):
        """
        このパスが示すファイルがディレクトリであるか検証する
        """
        return os.path.isdir(self)
    
    def exists(self):
        """
        このパスが示すファイルが存在するか検証する
        """
        return os.path.exists(self)
    
    def touch(self, isdir = True):
        """
        このパスが示すファイルを生成する
        """
        if isdir:
            if not self.isdir():
                os.makedirs(self.fsstr)
        elif not self.isfile():
            open(self, "wb").close()
    
    def to_fsstr(self):
        """
        この実行環境上の `text_type` へキャストする;
        必要であればファイルシステムの文字エンコーディングで変換される
        """
        if PY2:
            return self.encode(fsencoding, self.errors)
        else:
            return text_type(self) # casting only
    
    fsstr = property(to_fsstr)
    
    def to_text(self):
        """
        `text_type` へキャストする;
        この操作はいかなる文字エンコーディングの変更も行わない
        """
        return text_type(self) # casting only
    
    text = property(to_text)
    
    def abspath(self, user = True, env = True):
        """
        このパスの絶対パスを解決し、その文字列で初期化された新たなインスタンスを得る
        """
        s = self.fsstr
        if user: s = os.path.expanduser(s)
        if env: s = os.path.expandvars(s)
        s = os.path.abspath(s)
        return self.cls(s, **self.__dict__)
    
    def relpath(self, start, ensure_abspath = False):
        """
        このパスの `start` からの相対パスを解決し、その文字列で初期化された新たなインスタンスを得る
        """
        if not isinstance(start, self.cls):
            start = self.cls(start, **self.__dict__)
        if ensure_abspath:
            p1 = self.abspath().fsstr
            p2 = start.abspath().fsstr
        else:
            p1 = self.fsstr
            p2 = start.fsstr
        return self.cls(os.path.relpath(p1, p2), **self.__dict__)
    
    def basename(self):
        """
        このパスの終端のファイル要素を表すパス(ファイル名)を得る
        """
        return self.cls(os.path.basename(self.fsstr), **self.__dict__)
    
    def name_ext_tuple(self):
        """
        このパスの終端のファイル要素を表すパス(ファイル名)のうち、拡張子を除いた名前と拡張子からなるタプルを得る;
        拡張子が含まれない場合は、拡張子部分は空文字列となる
        """
        n, e = os.path.splitext(self.basename())
        if e: e = e[1:] # remove first os.extsep
        return n, e
    
    def namepart(self):
        """
        このパスの終端のファイル要素を表すパス(ファイル名)のうち、拡張子を除いた名前を得る
        """
        return self.name_ext_tuple()[0]
    
    def extpart(self):
        """
        このパスの終端のファイル要素を表すパス(ファイル名)のうち、拡張子を得る;
        ファイル名に拡張子が含まれない場合は空の文字列が返却される
        """
        return self.name_ext_tuple()[1]
    
    def dirname(self, nth = 1):
        """
        このパスのディレクトリ要素を表すパスを得る
        """
        s = self.fsstr
        while nth > 0:
            s = os.path.dirname(s)
            nth -= 1
        return self.cls(s, **self.__dict__)
    
    def components(self, ensure_abspath = False):
        """
        このパスのディレクトリ、ファイル(拡張子除)、拡張子に分解した 3-tupleを返却する
        """
        p = self.abspath() if ensure_abspath else self
        dn = p.dirname()
        name, ext = self.name_ext_tuple()
        return dn, name, ext
    
    def replaced(self, dirname = None, namepart = None, extpart = None, ensure_abspath = True):
        """
        このパスのディレクトリ、ファイル(拡張子除)、拡張子を
        """
        p = self.abspath() if ensure_abspath else self
        dn, name, ext = p.components()
        if dirname is not None: dn = self.ensure(dirname)
        if namepart is not None: name = namepart
        if extpart is not None: ext = extpart
        
        name_ext = "%s%s%s" % (name, os.extsep, ext) if ext else name
        if name_ext:
            return dn.join(name_ext)
        else:
            return dn if not dn.endswith("/") else self.ensure(dn[:-1])
    
    def join(self, *subpath):
        """
        このパスに後続のファイル要素を連結したパスを得る
        """
        return self.cls(self, *subpath, **self.__dict__)
    
    def list(self, recursive_check = (lambda adir, depth = 0: False), depth = 0):
        """
        このパスをディレクトリと見なした場合の、そのディレクトリに含まれるファイルのパスを列挙する
        """
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
        """
        このパスをファイルとみなした場合の、そのファイルのコンテンツを得る;
        encodingが指定されている場合は `text_type` として、そうでなければ `bytes_type` として返却される
        """
        if encoding:
            return codecs.open(self, "rU", encoding, errors).read()
        else:
            return open(self, "rb").read()

class ZipOutput(object):
    """
    :class:`zipfile.ZipFile` を用いた ZIPファイルへの書き込みをラップしたもの
    """
    def __init__(self, zipfilename = None, compress = zipfile.ZIP_DEFLATED):
        """
        対象のファイル名、または一時ファイルとして初期化する
        """
        self.__out = zipfile.ZipFile(zipfilename or tempfile.NamedTemporaryFile("wb", delete = False), "w", compress, True)
        self.__is_tempfile = zipfilename is None
        self.__filename = FilePath.ensure(self.__out.filename)
        self.packed = set()
    
    @property
    def is_tempfile(self):
        """
        書き込み先のファイルが一時ファイルであるかを表す
        """
        return self.__is_tempfile
    
    @property
    def raw_zipfile(self):
        """
        (internal) このオブジェクトで使用される :class:`zipfile.ZipFile` を得る
        """
        return self.__out
    
    @property
    def filename(self):
        """
        書き込み先のファイルパスを得る
        """
        return self.__filename
    
    def close(self):
        """
        ZIPファイルへの書き込みを完了する
        """
        if self.is_closed:
            return
        self.__out.close()
        self.__out = None
    
    @property
    def is_closed(self):
        """
        ZIPファイルへの書き込みが完了しているかを表す
        """
        return self.__out is None
    
    @contextlib.contextmanager
    def finishing(self):
        """
        ZIPファイルへの書き込みを完了し、自身を返却する `ContextManager` を得る;
        
        .. code-block::
        
            azip = ZipOutput() # 一時ファイルでZIPファイルを生成
            azip.writetext("foo.txt", u"abcdef")
            with azip.finishing():
                # azipへの書き込みは完了されるが、一時ファイルは削除されていないため、
                # azip.filename が指すファイルの終了処理を行う
                pass
            # この時点で一時ファイルが削除されている
        """
        assert not self.is_closed
        self.close()
        yield self
        if self.is_tempfile:
            print("(remove tempfile %s)" % self.filename)
            os.remove(self.filename)
    
    def __enter__(self):
        return self
    
    def __exit__(self, etype, einst, etrace):
        self.close()
    
    def writefile(self, srcfile, arcname = None):
        """
        `zipfile.Zipfile.write` のように既存のファイルをこの ZIPへ追加する
        """
        if arcname is None:
            os.path.basename(srcfile)
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__out.write(srcfile, arcname)
    
    def writebytes(self, arcname, abytes = b""):
        """
        `zipfile.ZipFile.writestr` のように ZIPへ追加する
        """
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__out.writestr(arcname, ensure_bytes(abytes))
    
    def writetext(self, arcname, texts = "", encoding = "utf-8", errors = "strict"):
        """
        `zipfile.ZipFile.writestr` へ `text_type` を与えたかのように ZIPへ追加する
        """
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__out.writestr(arcname, ensure_bytes(texts, encoding, errors))
    
    @contextlib.contextmanager
    def open(self, arcname, mode = "wb"):
        """
        ZIPへ追加されるバッファ用の一時ファイルを生成し、それを返却する `ContextManager`
        """
        with tempfile.NamedTemporaryFile(mode, delete = False) as tempf:
            yield tempf
            tempf.close()
            if not arcname in self.packed:
                self.packed.add(arcname)
                self.__out.write(tempf.name, arcname)
            os.remove(tempf.name)

class WrappedBlobWriter(object):
    """
    :class:`blobstore.BlobWriter` を用いた BLOBファイルへの書き込みをラップしたもの
    """
    def __init__(self, blobfilename = None):
        """
        対象のファイル名、または一時ファイルとして初期化する
        """
        self.__out = blobstore.BlobWriter(blobfilename or tempfile.NamedTemporaryFile("wb", delete = False).name)
        self.__is_tempfile = blobfilename is None
        self.__filename = FilePath.ensure(self.__out.filename)
        self.packed = set()
    
    @property
    def is_tempfile(self):
        """
        書き込み先のファイルが一時ファイルであるかを表す
        """
        return self.__is_tempfile
    
    @property
    def raw_blobwriter(self):
        """
        (internal) このオブジェクトで使用される :class:`blobstore.BlobWriter` を得る
        """
        return self.__out
    
    @property
    def filename(self):
        """
        書き込み先のファイルパスを得る
        """
        return self.__filename
    
    def close(self):
        """
        書き込みを完了する
        """
        if self.is_closed:
            return
        self.__out.close()
        self.__out = None
    
    @property
    def is_closed(self):
        """
        書き込みが完了しているかを表す
        """
        return self.__out is None
    
    @contextlib.contextmanager
    def finishing(self):
        """
        書き込みを完了し、自身を返却する `ContextManager` を得る
        """
        assert not self.is_closed
        self.close()
        yield self
        if self.is_tempfile:
            print("(remove tempfile %s)" % self.filename)
            os.remove(self.filename)
    
    def __enter__(self):
        return self
    
    def __exit__(self, etype, einst, etrace):
        self.close()
    
    def writefile(self, srcfile, arcname = None):
        """
        `zipfile.Zipfile.write` のように既存のファイルをこの ZIPへ追加する
        """
        if arcname is None:
            os.path.basename(srcfile)
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__out.writefile(srcfile, arcname)
    
    def writebytes(self, arcname, abytes = b""):
        """
        バイト列を書き込む
        """
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__out.writebytes(arcname, ensure_bytes(abytes))
    
    def writetext(self, arcname, texts = "", encoding = "utf-8", errors = "strict"):
        """
        文字列を書き込む
        """
        if not arcname in self.packed:
            self.packed.add(arcname)
            self.__out.writebytes(arcname, ensure_bytes(texts, encoding, errors))
    
    @contextlib.contextmanager
    def open(self, arcname, mode = "wb"):
        """
        バッファを作成して書き込む
        """
        with tempfile.NamedTemporaryFile(mode, delete = False) as tempf:
            yield tempf
            tempf.close()
            if not arcname in self.packed:
                self.packed.add(arcname)
                self.__out.writefile(tempf.name, arcname)
            os.remove(tempf.name)