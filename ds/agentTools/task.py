#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 02:14
# @Author  : Wu_RH
# @FileName: task.py
import atexit
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
import ctypes
from ctypes import wintypes

from ds.agentTools import TOOLS
from ds.config import CONFIG

# ---------- Windows Job Object 管理（所有后台进程共享同一个作业） ----------
_job_handle = None
_job_initialized = False

# ---------- 后台进程管理（后备清理） ----------
_background_processes = []
_atexit_registered = False


def _cleanup_background_processes():
    for p in _background_processes:
        if p.poll() is None:
            _kill_process_tree(p, p.pid)


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


def _init_job_object():
    global _job_handle, _job_initialized
    if _job_initialized or sys.platform != "win32":
        return
    _job_initialized = True

    kernel32 = ctypes.windll.kernel32
    _job_handle = kernel32.CreateJobObjectW(None, None)
    if not _job_handle:
        return

    # 必须显式清零所有字段，否则 SetInformationJobObject 可能失败
    info = _JOBOBJECT_BASIC_LIMIT_INFORMATION()
    info.PerProcessUserTimeLimit = 0
    info.PerJobUserTimeLimit = 0
    info.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    info.MinimumWorkingSetSize = 0
    info.MaximumWorkingSetSize = 0
    info.ActiveProcessLimit = 0
    info.Affinity = 0
    info.PriorityClass = 0
    info.SchedulingClass = 0

    result = kernel32.SetInformationJobObject(
        _job_handle,
        2,  # JobObjectBasicLimitInformation
        ctypes.byref(info),
        ctypes.sizeof(info)
    )
    if not result:
        # 失败则释放句柄，并置 None，此时会降级到 atexit 清理
        kernel32.CloseHandle(_job_handle)
        _job_handle = None


def resolve_path(file_path):
    p = Path(file_path)
    if p.is_absolute():
        return str(p)
    return str(Path(CONFIG["WORKING_DIR"]) / p)


def truncate(s, max_len=None):
    if max_len is None:
        max_len = CONFIG["MAX_OUTPUT_LENGTH"]
    s = str(s)
    if len(s) <= max_len:
        return s
    half = max_len // 2
    return s[:half] + f"\n\n⚠ [输出已截断 — 共 {len(s):,} 字符，仅显示开头和结尾各 {half} 字符]\n\n" + s[-half:]


def _kill_process_tree(process, pid):
    """强杀进程树（平台相关）"""
    if process.poll() is not None:
        return  # 已结束

    if sys.platform == "win32":
        # Windows: 使用 taskkill /F /T 强制终结整个进程树
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=2
            )
        except Exception:
            # 备用方案：直接用 process.kill()
            process.kill()
    else:
        # Unix: 发送 SIGKILL 到整个进程组
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # 进程已退出
        except Exception:
            # 如果进程组无效，降级为单独 kill
            process.kill()


def _fix_windows_start_command(command):
    """
    在 Windows 下自动修复 start 命令：若命令以 'start' 开头且缺少标题参数，
    则在 /B 后插入空标题 ""，避免被误解为窗口标题。
    """
    if sys.platform != "win32":
        return command

    # 分割命令（保留引号）
    import shlex
    parts = shlex.split(command, posix=False)
    if not parts or parts[0].lower() != "start":
        return command

    # 如果命令只有 "start"，或已经带有标题（以非选项开头），不做强制插入
    # 但为了安全，统一在第一个选项之后插入空标题
    # 查找第一个选项（以 / 或 - 开头）
    opt_index = -1
    for i, part in enumerate(parts[1:], start=1):
        if part.startswith('/') or part.startswith('-'):
            opt_index = i
            break

    if opt_index == -1:
        # 没有选项：直接插入空标题在命令前
        parts.insert(1, "")
    else:
        # 在选项之后插入空标题（如果该位置已经有一个参数且不是选项，则认为是已有标题，不覆盖）
        # 但为保险，仍插入空标题（因为已有的可能被误解）
        # 检查 opt_index+1 是否越界，或下一个参数不是选项
        if len(parts) <= opt_index + 1:
            parts.insert(opt_index + 1, "")
        else:
            next_part = parts[opt_index + 1]
            # 如果下一个参数不是选项，则它可能被误认为标题，我们强制插入空标题并后移
            if not (next_part.startswith('/') or next_part.startswith('-')):
                parts.insert(opt_index + 1, "")
            else:
                # 如果下一个参数是选项，则说明后面没有标题，直接插入空标题
                parts.insert(opt_index + 1, "")

    return " ".join(parts)


# 11. run_command
def tool_run_command(command, cwd=None, timeout=60, env=None, wait=True):
    """
    执行 shell 命令并返回其输出。默认在工作目录中运行。

    新增参数：
        wait (bool): 是否等待命令结束并获取输出。
                     若为 False，则命令在后台运行（用户需自行保证命令能后台执行），
                     工具立即返回启动信息，不捕获输出也不超时。
                     默认为 True，保持原有行为。
    """
    # 自动修复 Windows start 命令
    if sys.platform == "win32":
        command = _fix_windows_start_command(command)

    work_dir = resolve_path(cwd) if cwd else CONFIG["WORKING_DIR"]
    env_vars = {**os.environ, **(env or {})}
    process = None
    timed_out = threading.Event()

    def force_kill():
        """超时强杀回调"""
        timed_out.set()
        if process and process.poll() is None:
            _kill_process_tree(process, process.pid)

    try:
        # 创建进程
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env_vars,
                creationflags=creation_flags,
            )
        else:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env_vars,
                start_new_session=True,
            )

        # 如果不等待，则直接返回（不启动定时器，不调用 communicate）
        if not wait:
            # 使用作业对象（Windows 强制终止时清理）
            if sys.platform == "win32":
                _init_job_object()
                if _job_handle:
                    kernel32 = ctypes.windll.kernel32
                    pid = process.pid
                    # 必须拥有 PROCESS_SET_QUOTA (0x0100) 和 PROCESS_TERMINATE (0x0001)
                    desired = 0x0100 | 0x0001 | 0x0400  # 含 QUERY_INFORMATION 便于调试
                    handle = kernel32.OpenProcess(desired, False, pid)
                    if handle:
                        ret = kernel32.AssignProcessToJobObject(_job_handle, handle)
                        kernel32.CloseHandle(handle)
                        # 若 ret=0，作业对象分配失败，但 atexit 会兜底
                        if not ret:
                            # 可选：记录日志，不影响执行
                            from ds.logger import LOGGER
                            LOGGER.warn(f"AssignProcessToJobObject 失败 (PID: {pid})，将依赖 atexit 清理")
                    else:
                        # 无法打开进程句柄，静默忽略
                        pass

            # 后备清理：父进程正常退出时（含 Ctrl+C）杀死所有后台进程
            _background_processes.append(process)
            global _atexit_registered
            if not _atexit_registered:
                atexit.register(_cleanup_background_processes)
                _atexit_registered = True

            time.sleep(0.2)
            return f"后台命令已启动 (PID: {process.pid})"

        # 启动超时定时器
        timer = threading.Timer(timeout, force_kill)
        timer.daemon = True
        timer.start()

        # 等待进程结束
        stdout, stderr = process.communicate()
        timer.cancel()

        # 若因超时而强杀，抛出异常
        if timed_out.is_set():
            output = stdout + stderr
            raise RuntimeError(f"最后输出：\n{truncate(output or '无输出')}\n命令执行超时（{timeout} 秒），已被强制终止")

        output = stdout + stderr
        if process.returncode != 0:
            raise RuntimeError(
                f"命令执行失败（退出码 {process.returncode}）：\n{truncate(output or '无输出')}"
            )
        return truncate(output.strip() or "(命令执行成功，无输出)")

    except Exception as e:
        raise RuntimeError(f"命令执行错误: {e}")

    finally:
        # 确保进程被清理（若因异常未终止且 wait=True 或进程还在运行）
        if wait and process and process.poll() is None:
            _kill_process_tree(process, process.pid)
        # 若 wait=False，不清理，让进程在后台继续


# ===== 更新 TOOLS["run_command"] 定义 =====
TOOLS["run_command"] = {
    "description": "执行 shell 命令并返回其输出。默认在工作目录中运行。若设置 wait=False，则命令在后台运行（仅适用于 Windows 的 start /B 或 Unix 的 & 方式），不等待结果。",
    "parameters": {
        "command": {"type": "string", "required": True, "description": "要执行的 shell 命令"},
        "cwd": {"type": "string", "required": False, "description": "命令的工作目录"},
        "timeout": {"type": "number", "required": False, "description": "超时时间（秒），默认 60，仅当 wait=True 时有效"},
        "env": {"type": "object", "required": False, "description": "额外的环境变量（键值对）"},
        "wait": {"type": "boolean", "required": False, "description": "是否等待命令完成并返回输出，默认 True。设为 False 时命令后台运行，立即返回。"},
    },
    "execute": tool_run_command,
}


# 16. run_test
def tool_run_test():
    test_path = CONFIG.get("TEST_BAT_PATH")
    if not test_path:
        # 没有测试脚本，视为通过
        return {"success": True, "data": "测试通过"}
    abs_test = Path(test_path)
    if not abs_test.exists():
        return {"success": True, "data": "测试通过"}
    try:
        # Windows 下 .bat 文件需要用 shell=True
        result = subprocess.run(
            str(abs_test),
            shell=True,
            cwd=CONFIG["WORKING_DIR"],
            capture_output=True,
            text=True,
            env={**os.environ, "DSA_LOG_FILE": os.environ.get("DSA_LOG_FILE", "")}
        )
        output = result.stdout + "\n" + result.stderr
        lines = output.splitlines()
        last_hundred = "\n".join(lines[-100:])
        if result.returncode == 0:
            return {"success": True, "data": f"测试成功（退出码 {result.returncode}）：\n{last_hundred}"}
        else:
            return {"success": False, "data": f"测试失败（退出码 {result.returncode}）：\n{last_hundred}"}
    except Exception as e:
        return {"success": False, "data": f"测试执行异常: {e}"}


TOOLS["run_test"] = {
    "description": "如果认为任务已完成，调用此工具执行测试脚本(无指定参数)，测试通过则任务完成，失败则返回错误信息。",
    "parameters": {},
    "execute": tool_run_test,
}


def tool_abort_task(reason, errorCode):
    from ds.logger import LOGGER
    LOGGER.info(f"\n🚨 [中止] AI 请求中止任务。原因：{reason}")
    LOGGER.info(f"以错误码 {errorCode} 退出。")
    return {"success": True, "data": f"{errorCode}"}


TOOLS["abort_task"] = {
    "description": "强制中止当前任务并以指定的错误码退出代理。当遇到致命错误、无效需求或任何不可恢复的情况时使用；若需正常结束任务，可将错误码设为 0。",
    "parameters": {
        "reason": {"type": "string", "required": True, "description": "中止任务的原因"},
        "errorCode": {"type": "integer", "required": True, "description": "退出时使用的错误码。设置为 0 表示正常退出，非零表示异常退出。"}
    },
    "execute": tool_abort_task,
}

if __name__ == "__main__":
    def main():
        result = tool_run_command(
            "ping -t 127.0.0.1", wait=False
        )
        print(result)
        print(result)

    main()

