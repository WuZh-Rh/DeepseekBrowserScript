#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/10/09 00:31
# @Author  : Wu_RH
# @FileName: utils.py.py

import base64
import os
import shutil


def decode_line(line: bytes) -> str:
    if not line:
        return ""
    try:
        return line.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return line.decode('gbk')
    except UnicodeDecodeError:
        pass
    u8 = line.decode('utf-8', errors='replace')
    gb = line.decode('gbk', errors='replace')
    return u8 if u8.count('\ufffd') <= gb.count('\ufffd') else gb


def decode_bytes(data: bytes) -> str:
    if not data:
        return ""
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return data.decode('gbk')
    except UnicodeDecodeError:
        pass
    return '\n'.join(decode_line(p) for p in data.split(b'\n'))


def find_powershell() -> str:
    """定位可用的 PowerShell（优先 pwsh 7，回退 Windows PowerShell 5.1）。"""
    for name in ("pwsh.exe", "pwsh", "powershell.exe", "powershell"):
        p = shutil.which(name)
        if p:
            return p
    fallback = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if os.path.exists(fallback):
        return fallback
    raise RuntimeError("找不到 PowerShell，无法在 Windows 上执行命令")


def wrap_powershell(command: str, utf8_output: bool = True) -> list:
    """
    把整条命令包成 PowerShell -EncodedCommand 调用，返回可直接交给
    subprocess.Popen(args, shell=False) 的参数列表。

    用途：绕开 Windows 上 shell=True 时 cmd.exe 对引号/元字符的二次解析。
    命令以 UTF-16LE base64 编码传递，cmd/pwsh 层看不到任何特殊字符。
    """
    script = command
    if utf8_output:
        script = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script
    b64 = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return [
        find_powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        b64,
    ]
