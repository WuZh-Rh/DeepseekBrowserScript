#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:31
# @Author  : Wu_RH
# @FileName: logger.py
# src/logger.py

import logging
import os
import json
import re
import sys
from logging import FileHandler, Formatter, StreamHandler
from typing import Any, Optional, Dict, List
from datetime import datetime
from pathlib import Path

os.system("")

__all__ = [
    "LOGGER",
    "Logger",
    "getLogger",
    "SELF_PATH",
    "ANSI_COLORS",
    "LOGGER_MASTER",
    "trunc_display",
    "json_preview",
]

SELF_PATH: str = os.getcwd()
LOGGER_MASTER_NAME: str = "Logger"

ANSI_COLORS: Dict[str, str] = {
    'BLACK': '\033[30m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'BRIGHT_BLACK': '\033[90m',
    'BRIGHT_RED': '\033[91m',
    'BRIGHT_GREEN': '\033[92m',
    'BRIGHT_YELLOW': '\033[93m',
    'BRIGHT_BLUE': '\033[94m',
    'BRIGHT_MAGENTA': '\033[95m',
    'BRIGHT_CYAN': '\033[96m',
    'BRIGHT_WHITE': '\033[97m',
    'RESET': '\033[0m',
    'BOLD': '\033[1m',
    'DIM': '\033[2m',
    'ITALIC': '\033[3m',
    'UNDERLINE': '\033[4m',
    'BLINK': '\033[5m',
    'REVERSE': '\033[7m',
    'HIDDEN': '\033[8m',
    'BG_BLACK': '\033[40m',
    'BG_RED': '\033[41m',
    'BG_GREEN': '\033[42m',
    'BG_YELLOW': '\033[43m',
    'BG_BLUE': '\033[44m',
    'BG_MAGENTA': '\033[45m',
    'BG_CYAN': '\033[46m',
    'BG_WHITE': '\033[47m',
    'BG_BRIGHT_BLACK': '\033[100m',
    'BG_BRIGHT_RED': '\033[101m',
    'BG_BRIGHT_GREEN': '\033[102m',
    'BG_BRIGHT_YELLOW': '\033[103m',
    'BG_BRIGHT_BLUE': '\033[104m',
    'BG_BRIGHT_MAGENTA': '\033[105m',
    'BG_BRIGHT_CYAN': '\033[106m',
    'BG_BRIGHT_WHITE': '\033[107m',
}

# ----- 添加常用小写别名（方便调用） -----
ANSI_COLORS.update({
    'black': ANSI_COLORS['BLACK'],
    'red': ANSI_COLORS['RED'],
    'green': ANSI_COLORS['GREEN'],
    'yellow': ANSI_COLORS['YELLOW'],
    'blue': ANSI_COLORS['BLUE'],
    'magenta': ANSI_COLORS['MAGENTA'],
    'cyan': ANSI_COLORS['CYAN'],
    'white': ANSI_COLORS['WHITE'],
    'gray': ANSI_COLORS['BRIGHT_BLACK'],
    'grey': ANSI_COLORS['BRIGHT_BLACK'],
    'lblack': ANSI_COLORS['BRIGHT_BLACK'],
    'lred': ANSI_COLORS['BRIGHT_RED'],
    'lgreen': ANSI_COLORS['BRIGHT_GREEN'],
    'lyellow': ANSI_COLORS['BRIGHT_YELLOW'],
    'lblue': ANSI_COLORS['BRIGHT_BLUE'],
    'lmagenta': ANSI_COLORS['BRIGHT_MAGENTA'],
    'lcyan': ANSI_COLORS['BRIGHT_CYAN'],
    'lwhite': ANSI_COLORS['BRIGHT_WHITE'],
    # 也支持大写形式，但通常我们用小写调用
    'LGREEN': ANSI_COLORS['BRIGHT_GREEN'],
    'LRED': ANSI_COLORS['BRIGHT_RED'],
    'LCYAN': ANSI_COLORS['BRIGHT_CYAN'],
    'LBLUE': ANSI_COLORS['BRIGHT_BLUE'],
    'LYELLOW': ANSI_COLORS['BRIGHT_YELLOW'],
    'LMAGENTA': ANSI_COLORS['BRIGHT_MAGENTA'],
    'LWHITE': ANSI_COLORS['BRIGHT_WHITE'],
    'GRAY': ANSI_COLORS['BRIGHT_BLACK'],
})


def c(code: str, text: str) -> str:
    return f"{ANSI_COLORS[code.upper()]}{text}{ANSI_COLORS['RESET']}"


def cb(code: str, text: str) -> str:
    return f"{ANSI_COLORS['BOLD']}{ANSI_COLORS[code.upper()]}{text}{ANSI_COLORS['RESET']}"


def remove_colors(text: str) -> str:
    return re.sub(r'\033\[[0-9;]*m', '', text)


def local_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def trunc_display(s: Any, max_len: int = 400) -> str:
    s_str: str = str(s)
    if len(s_str) <= max_len:
        return s_str
    return s_str[:max_len] + c('gray', f'… (+{len(s_str) - max_len} 字符)')


def json_preview(obj: Any, max_len: int = 350) -> str:
    try:
        s: str = json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return trunc_display(s, max_len)


def _get_archive_path(log_dir: Path, roll_name: str = "") -> Path:
    """生成日期归档文件路径，索引自动递增，不移动任何已有文件"""
    date_str: str = datetime.now().strftime("%Y-%m-%d")
    date_dir: Path = log_dir / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    existing: List[Path] = [f for f in date_dir.iterdir() if f.suffix == '.log' and f.stem.startswith(date_str)]
    max_idx: int = -1
    for f in existing:
        if not f.name.startswith(date_str):
            continue
        # 提取日期后的四位数字索引，不管后面有没有后缀
        match = re.search(rf'^{date_str}-(\d{{4}})', f.name)
        if not match:
            continue
        idx = int(match.group(1))
        if idx > max_idx:
            max_idx = idx

    next_idx: int = max_idx + 1
    name: str = f"{date_str}-{next_idx:04d}"
    if roll_name:
        name += f"-{roll_name}"
    name += ".log"
    return date_dir / name


class PlainFileFormatter(Formatter):
    def format(self, record: logging.LogRecord) -> str:
        s: str = super().format(record)
        return remove_colors(s)


class Logger(logging.Logger):
    def setLevel(self, level: int) -> None:
        for handler in self.handlers:
            if isinstance(handler, StreamHandler):
                handler.setLevel(level)
                break

    def setFileLevel(self, level: int) -> None:
        for handler in self.handlers:
            if isinstance(handler, FileHandler):
                handler.setLevel(level)
                break

    def debug(self, msg: str, *args: object, **kwargs: Any) -> None:
        super().debug(msg, *args, **kwargs)
        formatted: str = msg % args if args else msg
        print(c('blue', formatted))

    def info(self, msg: str, *args: object, **kwargs: Any) -> None:
        super().info(msg, *args, **kwargs)
        formatted: str = msg % args if args else msg
        print(c('green', formatted))

    def warning(self, msg: str, *args: object, **kwargs: Any) -> None:
        super().warning(msg, *args, **kwargs)
        formatted: str = msg % args if args else msg
        print(c('yellow', formatted))

    def error(self, msg: str, *args: object, **kwargs: Any) -> None:
        super().error(msg, *args, **kwargs)
        formatted: str = msg % args if args else msg
        print(c('red', formatted))

    def critical(self, msg: str, *args: object, **kwargs: Any) -> None:
        super().critical(msg, *args, **kwargs)
        formatted: str = msg % args if args else msg
        print(c('bright_red', formatted))

    def warn(self, msg: str, *args: object, **kwargs: Any) -> None:
        self.warning(msg, *args, **kwargs)

    def banner(self) -> None:
        msg: str = f"""
{c('cyan', '=' * 52)}
{c('lcyan', 'DeepSeek 浏览器代理')}
{c('gray', '通过浏览器自动化实现的 AI 编码代理')}
{c('gray', '无需 API 密钥 — 使用 chat.deepseek.com')}
{c('cyan', '=' * 52)}
"""
        print(msg)
        self.info("BANNER:\n" + remove_colors(msg))

    def header(self, msg: str) -> None:
        line: str = '-' * 50
        output: str = f"\n{c('blue', line)}\n{c('bold', msg)}\n{c('blue', line)}\n"
        print(output)
        self.info("HEADER: " + remove_colors(output))

    def success(self, msg: str) -> None:
        print(c('lgreen', msg))
        self.info("SUCCESS: " + remove_colors(msg))

    def dim(self, msg: str) -> None:
        print(f"{ANSI_COLORS['DIM']}{msg}{ANSI_COLORS['RESET']}")
        self.info("DIM: " + remove_colors(msg))

    def thinking(self, msg: str) -> None:
        sys.stdout.write(c('gray', msg) + '\r')
        sys.stdout.flush()

    def clear_line(self) -> None:
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()

    def tool_call(self, name: str, args: Any) -> None:
        output: str = f"\n{c('magenta', '工具调用')} {c('cyan', f'-> {name}')}"
        print(output)
        preview: str = json_preview(args)
        if preview.strip():
            for line in preview.splitlines():
                print(f"  {c('gray', line)}")
        self.info("TOOL_CALL: " + remove_colors(name) + " " + str(args))

    def tool_result(self, result: str, is_error: bool = False) -> None:
        color: str = 'lred' if is_error else 'gray'
        print(c(color, "结果:"))
        lines: List[str] = trunc_display(str(result), 300).splitlines()[:12]
        for line in lines:
            print(f"  {c(color, line)}")
        if len(str(result).splitlines()) > 12:
            print(c('gray', '  … （为显示而截断）'))
        print()
        status: str = "ERROR" if is_error else "SUCCESS"
        self.info("TOOL_RESULT (" + status + "): " + remove_colors(str(result)[:500]))

    def final_output(self, msg: str) -> None:
        line: str = '━' * 50
        output: str = f"\n{c('lgreen', line)}\n{c('lgreen', '任务完成')}\n{c('lgreen', line)}\n\n{msg}\n"
        print(output)
        self.info("FINAL: " + remove_colors(output))

    def separator(self, label: str = '') -> None:
        pad: str = f" {label} " if label else ""
        out: str = f"\n{c('gray', '-' * 20 + pad + '-' * 20)}\n"
        print(out)
        self.info("SEPARATOR: " + remove_colors(out))

    def iteration(self, n: int, max_n: int) -> None:
        print(c('dim', f'第 {n}/{max_n} 步'))
        self.info("ITERATION: " + remove_colors(f'第 {n}/{max_n} 步'))


class LoggerMaster:
    logger_map: Dict[str, Logger] = {}

    def __init__(self) -> None:
        self.DEFAULT_CONFIG: Dict[str, Any] = {
            "format": "%(asctime)s   %(levelname)s\t[%(name)s]:\t%(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "logfile": f"{SELF_PATH}/log/latest.log",
            "level": logging.INFO,
            "file_level": logging.INFO,
            "roll_name": "",  # 归档文件名后缀，例如 "backend"
        }

    def getLogger(
        self,
        name: str = LOGGER_MASTER_NAME,
        logger_config: Optional[Dict[str, Any]] = None
    ) -> Logger:
        if name in self.logger_map:
            return self.logger_map[name]
        if logger_config is not None:
            self.DEFAULT_CONFIG.update(logger_config)
        config: Dict[str, Any] = self.DEFAULT_CONFIG.copy()

        log_path: str = config["logfile"]
        log_dir: Path = Path(log_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        logger: Logger = Logger(name)
        logger.setLevel(config["level"])

        # ----- 文件处理器 1: logfile (每次启动清空，mode='w') -----
        file_handler_main: FileHandler = FileHandler(log_path, mode='w', encoding='utf-8')
        file_handler_main.setLevel(config["file_level"])
        formatter_main: PlainFileFormatter = PlainFileFormatter(
            config["format"], datefmt=config["datefmt"]
        )
        file_handler_main.setFormatter(formatter_main)
        logger.addHandler(file_handler_main)

        # ----- 文件处理器 2: 日期归档文件 (追加，mode='a') -----
        archive_path: Path = _get_archive_path(log_dir, config.get("roll_name", ""))
        file_handler_archive: FileHandler = FileHandler(str(archive_path), mode='a', encoding='utf-8')
        file_handler_archive.setLevel(config["file_level"])
        formatter_archive: PlainFileFormatter = PlainFileFormatter(
            config["format"], datefmt=config["datefmt"]
        )
        file_handler_archive.setFormatter(formatter_archive)
        logger.addHandler(file_handler_archive)

        # ----- 控制台输出由 Logger 类的 print 方法实现，不添加 StreamHandler -----

        logger.info("=== 会话开始 ===")
        self.logger_map[name] = logger
        return logger


LOGGER_MASTER: LoggerMaster = LoggerMaster()
getLogger = LOGGER_MASTER.getLogger
LOGGER: Optional[Logger] = None
