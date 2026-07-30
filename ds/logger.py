#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:31
# @Author  : Wu_RH
# @FileName: logger.py.py
# src/logger.py

from datetime import datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Optional

# ANSI colors
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    "lred": "\033[91m",
    "lgreen": "\033[92m",
    "lyellow": "\033[93m",
    "lblue": "\033[94m",
    "lmagenta": "\033[95m",
    "lcyan": "\033[96m",
}


def c(code, text):
    return f"{COLORS[code]}{text}{COLORS['reset']}"


def cb(code, text):
    return f"{COLORS['bold']}{COLORS[code]}{text}{COLORS['reset']}"


def remove_colors(text):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', text)


def local_timestamp():
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# 文件日志
_log_stream: Optional[TextIOWrapper] = None
_log_is_fixed: bool = False


def init_log_file(log_path, is_fixed=False):
    global _log_stream, _log_is_fixed
    if _log_stream:
        return
    if not log_path:
        return
    try:
        if is_fixed:
            # 固定文件模式
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            _log_stream = open(log_file, 'a', encoding='utf-8')
            _log_stream.write(f"[{local_timestamp()}] === 会话开始 ===\n")
            _log_stream.flush()
            logger.info(f"[Logger] 日志写入固定文件: {log_file}")
        else:
            # 滚动模式
            log_dir = Path(log_path)
            log_dir.mkdir(parents=True, exist_ok=True)
            latest_path = log_dir / "latest.log"
            # 归档旧日志
            if latest_path.exists():
                mtime = datetime.fromtimestamp(latest_path.stat().st_mtime)
                date_str = mtime.strftime("%Y-%m-%d")
                date_dir = log_dir / date_str
                date_dir.mkdir(exist_ok=True)
                # 找最大索引
                existing = [f for f in date_dir.iterdir() if f.suffix == '.log' and f.stem.startswith(date_str)]
                max_idx = -1
                for f in existing:
                    parts = f.stem.split('-')
                    if len(parts) >= 2:
                        try:
                            idx = int(parts[-1])
                            if idx > max_idx:
                                max_idx = idx
                        except:
                            pass
                next_idx = max_idx + 1
                archived_name = f"{date_str}-{next_idx:04d}.log"
                archived_path = date_dir / archived_name
                latest_path.rename(archived_path)
                logger.info(f"[Logger] 已归档旧日志: {archived_name}")
            # 创建新的 latest.log
            _log_stream = open(latest_path, 'a', encoding='utf-8')
            _log_stream.write(f"[{local_timestamp()}] === 会话开始 ===\n")
            _log_stream.flush()
            logger.info(f"[Logger] 日志写入滚动文件: {latest_path}")
        _log_is_fixed = is_fixed
    except Exception as e:
        logger.error(f"[Logger] 无法初始化文件日志: {e}")


def write_to_file(message, prefix_timestamp=True):
    if not _log_stream or message is None:
        return
    try:
        ts = local_timestamp()
        for line in str(message).splitlines():
            if prefix_timestamp:
                _log_stream.write(f"[{ts}] {line}\n")
            else:
                _log_stream.write(f"{line}\n")
        _log_stream.flush()
    except:
        pass


def trunc_display(s, max_len=400):
    s = str(s)
    if len(s) <= max_len:
        return s
    return s[:max_len] + c('gray', f'… (+{len(s) - max_len} 字符)')


def json_preview(obj, max_len=350):
    import json
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    return trunc_display(s, max_len)


class Logger:
    @staticmethod
    def banner():
        msg = f"""
{c('cyan', '=' * 52)}
{cb('lcyan', 'DeepSeek 浏览器代理')}
{c('gray', '通过浏览器自动化实现的 AI 编码代理')}
{c('gray', '无需 API 密钥 — 使用 chat.deepseek.com')}
{c('cyan', '=' * 52)}
"""
        print(msg)
        write_to_file("BANNER:" + remove_colors(msg), False)

    @staticmethod
    def header(msg):
        line = '-' * 50
        output = f"\n{c('blue', line)}\n{c('bold', '📋 ')}{cb('white', msg)}\n{c('blue', line)}\n"
        print(output)
        write_to_file("HEADER: " + remove_colors(output), False)

    @staticmethod
    def info(msg):
        out = f"{c('lblue', 'INFO ')} {msg}"
        print(out)
        write_to_file("INFO: " + remove_colors(msg))

    @staticmethod
    def success(msg):
        out = f"{c('lgreen', '  ✓ ')} {c('lgreen', msg)}"
        print(out)
        write_to_file("SUCCESS: " + remove_colors(msg))

    @staticmethod
    def warn(msg):
        out = f"{c('lyellow', '  ⚠ ')} {c('lyellow', msg)}"
        print(out)
        write_to_file("WARN: " + remove_colors(msg))

    @staticmethod
    def error(msg):
        out = f"{c('lred', '  ✗ ')} {c('lred', msg)}"
        print(out)
        write_to_file("ERROR: " + remove_colors(msg))

    @staticmethod
    def dim(msg):
        out = f"{COLORS['dim']}    {msg}{COLORS['reset']}"
        print(out)
        write_to_file("DIM: " + remove_colors(msg))

    @staticmethod
    def thinking(msg):
        import sys
        sys.stdout.write(f"  {c('cyan', '⟳')} {c('gray', msg)}\r")
        sys.stdout.flush()

    @staticmethod
    def clear_line():
        import sys
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()

    @staticmethod
    def tool_call(name, args):
        output = f"\n  {cb('magenta', '⚡ 工具调用')} {c('cyan', f'→ {name}')}"
        print(output)
        preview = json_preview(args)
        if preview.strip():
            for line in preview.splitlines():
                print(f"  {c('gray', line)}")
        write_to_file("TOOL_CALL: " + remove_colors(name) + " " + str(args))

    @staticmethod
    def tool_result(result, is_error=False):
        icon = c('lred', '  ✗ 结果:') if is_error else c('lgreen', '  ✓ 结果:')
        color = 'lred' if is_error else 'gray'
        print(icon)
        lines = trunc_display(str(result), 300).splitlines()[:12]
        for line in lines:
            print(f"  {c(color, line)}")
        if len(str(result).splitlines()) > 12:
            print(f"  {c('gray', '  … （为显示而截断）')}")
        print()
        write_to_file("TOOL_RESULT (" + ("ERROR" if is_error else "SUCCESS") + "): " + remove_colors(str(result)[:500]))

    @staticmethod
    def final_output(msg):
        line = '━' * 50
        output = f"\n{c('lgreen', line)}\n{cb('lgreen', '✅  任务完成')}\n{c('lgreen', line)}\n\n{msg}\n"
        print(output)
        write_to_file("FINAL: " + remove_colors(output), False)

    @staticmethod
    def separator(label=''):
        pad = f" {label} " if label else ""
        out = f"\n{c('gray', '·' * 20 + pad + '·' * 20)}\n"
        print(out)
        write_to_file("SEPARATOR: " + remove_colors(out), False)

    @staticmethod
    def iteration(n, max_n):
        out = f"\n{c('gray', '  ┄')} {c('dim', f'第 {n}/{max_n} 步')} {c('gray', '┄')}"
        print(out)
        write_to_file("ITERATION: " + remove_colors(out), False)


logger: Logger = Logger()
