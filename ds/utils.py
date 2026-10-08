#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/10/09 00:31
# @Author  : Wu_RH
# @FileName: utils.py.py

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