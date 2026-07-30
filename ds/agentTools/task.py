#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 02:14
# @Author  : Wu_RH
# @FileName: task.py
import os
import subprocess
import sys
from pathlib import Path

from ds.agentTools import TOOLS
from ds.config import config


def resolve_path(file_path):
    p = Path(file_path)
    if p.is_absolute():
        return str(p)
    return str(Path(config["WORKING_DIR"]) / p)


def truncate(s, max_len=None):
    if max_len is None:
        max_len = config["MAX_OUTPUT_LENGTH"]
    s = str(s)
    if len(s) <= max_len:
        return s
    half = max_len // 2
    return s[:half] + f"\n\n⚠ [输出已截断 — 共 {len(s):,} 字符，仅显示开头和结尾各 {half} 字符]\n\n" + s[-half:]


# 11. run_command
def tool_run_command(command, cwd=None, timeout=60, env=None):
    work_dir = resolve_path(cwd) if cwd else config["WORKING_DIR"]
    env_vars = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env_vars,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败（退出码 {result.returncode}）：\n{truncate(output or '无输出')}")
        return truncate(output.strip() or "(命令执行成功，无输出)")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"命令执行超时（{timeout} 秒）")
    except Exception as e:
        raise RuntimeError(f"命令执行错误: {e}")


TOOLS["run_command"] = {
    "description": "执行 shell 命令并返回其输出。默认在工作目录中运行。",
    "parameters": {
        "command": {"type": "string", "required": True, "description": "要执行的 shell 命令"},
        "cwd": {"type": "string", "required": False, "description": "命令的工作目录"},
        "timeout": {"type": "number", "required": False, "description": "超时时间（秒），默认 60"},
        "env": {"type": "object", "required": False, "description": "额外的环境变量（键值对）"},
    },
    "execute": tool_run_command,
}


# 16. run_test
def tool_run_test():
    test_path = config.get("TEST_BAT_PATH")
    if not test_path:
        # 没有测试脚本，视为通过
        return None
    abs_test = Path(test_path)
    if not abs_test.exists():
        return None
    try:
        # Windows 下 .bat 文件需要用 shell=True
        result = subprocess.run(
            str(abs_test),
            shell=True,
            cwd=config["WORKING_DIR"],
            capture_output=True,
            text=True,
            env={**os.environ, "DSA_LOG_FILE": os.environ.get("DSA_LOG_FILE", "")}
        )
        if result.returncode == 0:
            return None
        else:
            output = result.stdout + "\n" + result.stderr
            lines = output.splitlines()
            last_hundred = "\n".join(lines[-100:])
            return f"测试失败（退出码 {result.returncode}）：\n{last_hundred}"
    except Exception as e:
        return f"测试执行异常: {e}"


TOOLS["run_test"] = {
    "description": "如果认为任务已完成，调用此工具执行测试脚本(无指定参数)，测试通过则任务完成，失败则返回错误信息。",
    "parameters": {},
    "execute": tool_run_test,
}
