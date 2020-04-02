# encoding: utf-8
'''
Created on 20190905

@author: oreyou

* argparseとは異なる実装のコマンドラインツール

.. code-block::
    
    # 簡単な使用例
    class Cmd(SlackCommand): pass
    
    cmd = Cmd()
    @cmd.mark
    def f1(x, y):
        print(x, y)
    
    @cmd.mark
    def f2(a, b = 10):
        print(a, b)
    
    print(cmd.format_help().getvalue()) # or cmd.help() is directly outputs help into stdout
    
    cmd.parse("f1 1 2".split())()
    cmd.parse("f2 a".split())()
    
    c = cmd.parse("f2 a b=hoge".split())
    print(c.isvalid) # True
    c() # invokes f2("a", b="hoge")
    
    c = cmd.parse("invalid-command a b=hoge".split())
    print(c.isvalid) # False
    c() # raises NoSuchCommand error

.. code-block::

    # サブコマンドを使用した例
    class RootCommand(SlackCommand): pass
    class SubCommand1(SlackCommand): pass
    
    rootcmd = RootCommand()
    subcmd1 = rootcmd.add_subcommand("sub-cmd1", SubCommand1())
    subcmd2 = rootcmd.add_subcommand("sub-cmd2") # shorthand for rootcmd.add_subcommand("sub-cmd2", SlackCommand())
    
    @rootcmd.mark
    def root_f():
        print("root_f()")
    
    @subcmd1.mark
    def sub1_f():
        print("sub1_f()")
    
    @subcmd2.mark("sub2-f")
    def sub2_f():
        print("sub2_f()")
    
    rootcmd.parse("root_f".split())() # invokes root_f()
    rootcmd.parse("sub-cmd1 sub1_f".split())() # invokes sub1_f()
    rootcmd.parse("sub-cmd2 sub2-f".split())() # invokes sub2_f()
'''
from __future__ import absolute_import, print_function, unicode_literals

import functools
import inspect
import os
import sys

from amp.core import OrdDict
from amp.core.utils import StringIO, string_types, ensure_str, PY2


#from amp.core import StringIO, OrdDict, PY2, string_types, ensure_str
def help_to_stream(obj, output = None):
    """
    :func:`__builtin__.help` の呼び出しの結果を :class:`six.StringIO` として得るユーティリティ関数
    """
    if output is None:
        output = StringIO()
    stdout = sys.stdout
    sys.stdout = output
    help(obj)
    sys.stdout = stdout
    return output

class NoSuchCommand(Exception):
    """
    :func:`SlackCommand.parse` で対応するコマンドが検出できなかった場合に送出される例外
    """

class SlackCommand(object):
    """
    コマンドライン引数から関数を呼び出すことでコマンドラインインタフェースを提供するもの。
    
    """
    #: :func:`help` の出力で前書きとして付加される文字列
    prologue = None
    
    #: :func:`help` の出力で後書きとして付加される文字列
    epilogue = None
    
    def __init__(self, **kwds):
        self.registered = OrdDict()
        self.__dict__.update(kwds)
    
    @property
    def cls(self): return self.__class__
    
    def __str__(self):
        if PY2:
            return self.format_help().getvalue().encode(sys.stdout.encoding, "replaced")
        else:
            return self.format_help().getvalue()
    __repr__ = __str__
    
    def add(self, command_id, func):
        """
        対象のコマンド名に対して対象の呼び出し可能オブジェクトを登録する
        
        :param command_id: 対象のコマンド名
        :param func: 呼び出し可能オブジェクト
        :return: 呼び出し可能オブジェクト自体が返却される
        """
        func.base = getattr(func, "base", func)
        func.argspec = getattr(func, "argspec", inspect.getargspec(func))
        func.doc = getattr(func.base, "__doc__", "Call function %s with parameters %s" % (func.base.__name__, func.argspec.args))
        self.registered[command_id] = func
        return func
    
    def mark(self, func_or_name):
        """
        (デコレータとして使用) デコレーション対象の関数を登録する。
        引数なしでデコレートされた場合は、関数名が登録されるコマンド名となる。
        一方、文字列を渡した場合はそれがコマンド名として使用される。
        
        :param func_or_name: コマンドの実体を表す関数、またはコマンド名を表す文字列
        :return: デコレートされた関数、または関数デコレータ
        """
        # a function decorator
        if isinstance(func_or_name, string_types):
            def wrapper(func):
                return self.add(func_or_name, func)
            return wrapper
        else:
            return self.add(func_or_name.__name__, func_or_name)
    
    def help(self, *args, **kwargs):
        """
        登録済みのコマンドのヘルプメッセージを標準出力へ出力する。
        実際のヘルプメッセージの生成は :func:`format_help` へ委譲される。
        
        :param args: :func:`format_help` への位置引数
        :param kwargs: :func:`format_help` へのキーワード引数
        """
        if PY2:
            print(self.format_help(*args, **kwargs).getvalue().encode(sys.stdout.encoding, "replaced"))
        else:
            print(self.format_help(*args, **kwargs).getvalue())
    
    def format_help(
            self,
            out = None,
            command_id = None,
            linesep = os.linesep,
            commandsep = "=" * 20,
            command_format = "<{command_id}>",
            indent = "  |",
            encoding = "utf-8",
            **_
        ):
        """
        登録済みのコマンドのヘルプメッセージを生成する。
        FIXME: サブコマンドがあると少し挙動がおかしい
        
        :param out: 出力先のストリーム
        :param command_id: 出力するコマンド名、未指定ですべてのコマンドを対象にする
        :param linesep: 出力時の改行文字列
        :param commandsep: 出力時のコマンド間の分割文字列
        :param command_format: コマンド毎にコマンド名を受けて出力するフォーマット文字列
        :param indent: コマンドの出力時のインデント文字列
        :param ibw: (internal use) インデント付きの出力を行う機能
        """
        out = out or StringIO()
        sub_format_help_args = dict(locals())
        sub_format_help_args.pop("self")
        def get_doc_from(that):
            doc = None
            if that.__doc__:
                doc = that.__doc__
            elif isinstance(that, SlackCommand):
                doc = that.format_help(**sub_format_help_args).getvalue()
            if doc:
                return doc
            else:
                tmp = StringIO()
                help_to_stream(f, tmp)
                return tmp.getvalue()
        
        def write(a):
            out.write(ensure_str(a, encoding = encoding))
        
        def writeln(a):
            out.write(ensure_str(a, encoding = encoding))
            out.write(writeln.lineend)
        writeln.lineend = ensure_str(linesep, encoding = encoding)
        
        if self.prologue:
            writeln(self.prologue)
        
        if command_id is None:
            for command_id, f in self.registered.items():
                writeln(command_format.format(**locals()))
                writeln(get_doc_from(f))
                writeln(commandsep)
            writeln("all commands: %s" % list(self.registered.keys()))
        else:
            f = self.registered.get(command_id, None)
            if f is None:
                writeln("Unknown command %r: %s" % (command_id, list(self.registered.keys())))
            else:
                writeln(command_format.format(**locals()))
                write(get_doc_from(f))
        
        if self.epilogue:
            writeln(self.epilogue)
        return out
    
    def add_subcommand(self, command_id, command_instance = None, help = ""):  # @ReservedAssignment
        """
        別の :class:`SlackCommand` インスタンスをサブコマンドとして登録する
        
        :param command_id: サブコマンドとして登録するコマンド名
        :param command_instance: サブコマンドとして登録する :class:`SlackCommand` インスタンス、省略時は自動的に :class:`SlackCommand` インスタンスが生成される
        :return: 登録されたサブコマンドを表す :class:`SlackCommand` インスタンス
        """
        assert command_instance is None or isinstance(command_instance, SlackCommand), "{command_instance!r} is invalid object; should be a subclass of SlackCommand".format(**locals())
        if command_instance is None:
            command_instance = SlackCommand(__doc__ = help or "subcommand `{command_id}`".format(**locals()))
        # assert self is not command_instance, "cannot register myself; {command_instance} is self"
        assert not command_id in self.registered, "{command_id} is already registered".format(**locals())
        self.registered[command_id] = command_instance
        return command_instance
    
    def parse(self, command_args = None, keyword_sep = "=", dynamic_key_sep = "::", args_encoding = sys.stdin.encoding):
        """
        文字列のリストを受けて実行可能なコマンドを表す関数を得る。
        command_args[0]はコマンド名からコマンドの実体を表す関数を選択するために使われる。
        command_args[1:]は次のパターンで位置引数、キーワード引数、特殊な引数として収集される。
        
            (a = command_args[n]として)
            a が `keyword_sep` を含まない
            ==> a が `dynamic_key_sep` を含む => 特殊な引数として :func:`self._resolve_dynamic_key` へ渡された後に、キーワード引数として収集
            ||> それ以外 => 位置引数として収集
            a が `keyword_sep` を含む; `keyword_sep`の前後を k, vとする
            ==> k が `dynamic_key_sep` を含む => 特殊な引数として :func:`self._resolve_dynamic_key` へ渡された後に、キーワード引数として収集
            ||> それ以外 => キーワード引数として k, vを収集
        
        :param command_args: 文字列のリスト; 省略時は sys.argv[1:] とみなされる。また、文字列自体を渡すと例外が送出される。
        :param keyword_sep: キーワード引数のように扱われるコマンド引数のセパレータ
        :param dynamic_key_sep: :func:`self._resolve_dynamic_key` で解決される特殊なコマンド引数を表す際のセパレータ
        :return: 引数なしで評価可能な、コマンドを表す関数
        """
        assert not isinstance(command_args, string_types), "Ambiguous command arguments: string must be enclosed by list(): %r" % command_args
        if command_args is None:
            command_args = list(sys.argv[1:])
        
        if args_encoding:
            command_args = list(map((lambda a: ensure_str(a, encoding = args_encoding, errors = "strict")), command_args))
        args = []
        kwargs = {} # OrdDict()
        for a in command_args:
            kwpos = a.find(keyword_sep)
            if kwpos < 0:
                if a.find(dynamic_key_sep) >= 0:
                    # a; "func::key::word"
                    funcname_and_args = a.split(dynamic_key_sep)
                    key, value = self._resolve_dynamic_key(funcname_and_args[0], funcname_and_args[1:], None)
                    kwargs[key] = value
                else:
                    args.append(a)
            else:
                key, value = a.split(keyword_sep, 1)
                if key.find(dynamic_key_sep) >= 0:
                    # k; "func::key::word::is::found=value"
                    funcname_and_args = key.split(dynamic_key_sep)
                    key, value = self._resolve_dynamic_key(funcname_and_args[0], funcname_and_args[1:], value)
                kwargs[key] = value
        return self._parse_internal(args, kwargs)
    
    def _parse_internal(self, args, kwargs):
        "(internal use) 既に self.parseされた結果を受けてコマンドを呼び出せる形に変換する"
        if not args:
            def wrapped(*_, **__):
                raise NoSuchCommand(wrapped.__doc__)
            wrapped.__doc__ = "No command name: ({args}, {kwargs})".format(**locals())
            wrapped.isvalid = False
        else:
            fst, args = args[0], args[1:]
            func_or_subcmd = self.registered.get(fst, None)
            if not func_or_subcmd:
                def wrapped(*_, **__):
                    raise NoSuchCommand(wrapped.__doc__)
                commandkeys = list(self.registered.keys())
                wrapped.__doc__ = "{fst!r} is not registered command({args}, {kwargs}): set first args from one of {commandkeys}".format(**locals())
                wrapped.isvalid = False
            elif isinstance(func_or_subcmd, SlackCommand):
                # サブコマンドへ渡す
                return func_or_subcmd._parse_internal(args, kwargs) 
            else:
                @functools.wraps(func_or_subcmd)
                def wrapped(*_, **__):
                    return func_or_subcmd(*args, **kwargs)
                wrapped.isvalid = True
        return wrapped
    
    def _resolve_dynamic_key(self, funcname, args, value = None):
        """
        :func:`self.parse` で特殊な引数として扱われた際の、実際のキーワード引数への変換を行うもの
        パラメータの説明で `dynamic_key` は :func:`self.parse` の `dynamic_key_sep` で分割されたリストを指している。
        
        :param funcname: dynamic_key[0] を表すもの
        :param args: dynamic_key[1:] を表すもの
        :param value: 元の `keyword_sep` で分割された値を表すもの
        :return: キーワード引数として収集されるための、キーワード名とその値を指すタプル
        """
        raise NotImplementedError("returns (new key, new value) tuples for %s(%s)=%s" % (funcname, args, value))

