#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/08/22 22:26
# @Author  : Wu_RH
# @FileName: __init__.py

from ds.config import CONFIG


def init_tools():
    ext_tools = CONFIG.get("EXT_TOOLS", [])
    if any("wzq" in ext_tool for ext_tool in ext_tools):
        from ds.agentTools.broswer.gameHullqin import wzq


init_tools()
