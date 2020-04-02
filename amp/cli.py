# encoding: utf-8
'''
Created on 2020/03/27

@author: oreyou

* AMPのコマンドラインインタフェース
'''
from __future__ import absolute_import, print_function, unicode_literals

import functools
import sys
import zipfile

from amp.core import slackcommands, utils, siteconfig
import tempfile
import itertools
import os
import json

commands = slackcommands.SlackCommand()

@commands.mark("help")
def print_usage():
    "display this help messages"
    print(commands.format_help(encoding = utils.stdout_encoding).getvalue())

@commands.mark("config")
def make_config(config = None, output = "out.zip", sys_path = None, python_path = None, env_path = None):
    if sys_path: sys_path = sys_path.split(os.pathsep)
    if python_path: python_path = python_path.split(os.pathsep)
    if env_path: env_path = env_path.split(os.pathsep)
    siteconf = siteconfig.SiteConfiguration.autoconf(sys_path, python_path, env_path)
    siteconf.outputs = siteconfig.OutputConfiguration(filename = output)
    utils.open_or(sys.stdout, config, "wb").write(utils.ensure_bytes(utils.default_json_encoder.encode(siteconf)))
    return siteconf

def _target_classname_to_class(targets = None):
    if targets:
        targets = tuple(filter((lambda x: x is not None), (getattr(siteconfig, t) for t in targets.split())))
    if not targets:
        targets = object
    return targets

@commands.mark("show-targets")
def show_targets():
    for k in dir(siteconfig):
        v = getattr(siteconfig, k)
        if not isinstance(v, type):
            continue
        print(k)

@commands.mark("load")
def load_config(config = None):
    root = json.load(utils.open_or(sys.stdin, config, "r"))
    siteconf = siteconfig.SiteConfiguration.mount(root)
    return siteconf

@commands.mark("list")
def display_list(config = None, targets = None, output = None):
    siteconf = load_config(config)
    targets = _target_classname_to_class(targets)
    for ent in siteconf.iter_files(targets):
        print(ent)

@commands.mark("compose")
def compose(config = None, targets = None):
    siteconf = load_config(config)
    targets = _target_classname_to_class(targets)
    return siteconf.dump(targets)

if __name__ == '__main__':
    try:
        r = commands.parse(sys.argv[1:], args_encoding = getattr(sys.stdin, "encoding", sys.getdefaultencoding()))()
        if r is not None:
            print(r)
    except slackcommands.NoSuchCommand as nsc:
        print_usage()
        print(nsc)
