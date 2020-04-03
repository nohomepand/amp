# encoding: utf-8
'''
Created on 2020/03/27

@author: oreyou

* AMPのコマンドラインインタフェース
'''
from __future__ import absolute_import, print_function, unicode_literals

import collections
import functools
import itertools
import json
import os
import sys
import tempfile
import types
import zipfile

from amp.core import siteconfig, slackcommands, utils

commands = slackcommands.SlackCommand()

@commands.mark("help")
def print_usage():
    """
    Display this help messages
    """
    return commands.format_help(encoding = utils.stdout_encoding).getvalue()

@commands.mark("config")
def make_config(config = None, output = "out.zip", sys_path = None, python_path = None, env_path = None):
    """
    Create packaging configuration JSON file
    
    :param config: output JSON file path
    :param output: values for outputs.filename property
    :param sys_path: Python sys.path like string (may be splitted by os.pathsep); this values are replaced as `sys.path` if value is None (default).
    :param python_path: Environment variable `PYTHONPATH` like string (may be splitted by os.pathsep); this values are replaced as `os.environ["PYTHONPATH"]` if value is None (default).
    :param env_path: Environment variable `PATH` like string (may be splitted by os.pathsep); this values are replaced as `os.environ["PATH"]` if value is None (default).
    :return: instance of siteconfig.SiteConfiguration class
    """
    if sys_path: sys_path = sys_path.split(os.pathsep)
    if python_path: python_path = python_path.split(os.pathsep)
    if env_path: env_path = env_path.split(os.pathsep)
    siteconf = siteconfig.SiteConfiguration.autoconf(sys_path, python_path, env_path)
    siteconf.outputs = siteconfig.OutputConfiguration(filename = output)
    utils.open_or(sys.stdout, config, "wb").write(utils.ensure_bytes(utils.default_json_encoder.encode(siteconf)))
    return siteconf

def _target_classname_to_class(targets = None):
    """
    (internal)
    対象の文字列を空白で分割し、それぞれを `siteconfig` パッケージのクラス名と見なして変換したタプルを得る
    `list`、`compose` コマンドなどで使用
    """
    if targets:
        targets = tuple(filter(
            (lambda x: x is not None),
            (getattr(siteconfig, t, siteconfig.PackagesConfiguration.components().get(t, None)) for t in targets.split())
        ))
    if not targets:
        targets = object
    return targets

@commands.mark("show-targets")
def show_targets():
    """
    Get all of available names of target classes in the siteconfig packages.
    """
    for k in dir(siteconfig):
        v = getattr(siteconfig, k)
        if not isinstance(v, type):
            continue
        print(k)
    for k, cls in siteconfig.PackagesConfiguration.components().items():
        print(k, "as", cls.__name__)

@commands.mark("load")
def load_config(config = None):
    """
    Load packaging configuration JSON file.
    
    :param config: JSON file path; use sys.stdin when no file path is passed.
    :return: an instance of `siteconfig.SiteConfiguration`
    """
    root = json.load(utils.open_or(sys.stdin, config, "r"))
    siteconf = siteconfig.SiteConfiguration.mount(root)
    return siteconf

@commands.mark("list")
def display_list(config = None, targets = None):
    """
    Get file paths which is scanned by siteconfig.SiteConfiguration instance.
    The instance is loaded from `config` filepath by same manner of `load` command.
    
    :param config: configuration JSON file path
    :param targets: target class names in siteconfig packages
    """
    siteconf = load_config(config)
    targets = _target_classname_to_class(targets)
    return siteconf.iter_files(targets)

@commands.mark("compose")
def compose(config = None, targets = None):
    """
    Creates Application Module Package(AMP) file.
    Packaging files and output AMP file are specified by `config` JSON file.
    
    :param config: configuration JSON file path
    :param targets: target class names in siteconfig packages
    """
    siteconf = load_config(config)
    targets = _target_classname_to_class(targets)
    return siteconf.dump(targets)

if __name__ == '__main__':
    try:
        r = commands.parse(sys.argv[1:], args_encoding = getattr(sys.stdin, "encoding", sys.getdefaultencoding()))()
        if r is not None:
            if isinstance(r, dict):
                print(utils.default_json_encoder.encode(r))
            elif isinstance(r, (list, tuple, set, types.GeneratorType, collections.Iterable)) and not isinstance(r, utils.string_types):
                for ent in r:
                    print(ent)
            else:
                print(r)
    except slackcommands.NoSuchCommand as nsc:
        print_usage()
        print(nsc)
