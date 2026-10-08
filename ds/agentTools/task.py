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
from typing import BinaryIO, List, Optional

from ds.agentTools import TOOLS
from ds.config import CONFIG
from ds.utils import decode_bytes, wrap_powershell

# ---------- Windows Job Object 管理（所有后台进程共享同一个作业） ----------
_job_handle = None
_job_initialized = False

# ---------- 后台进程管理（后备清理 + 交互会话） ----------
_background_processes = []
_background_sessions = {}   # pid -> _BGSession
_atexit_registered = False


class _BGSession:
    """后台进程会话：保存进程对象、缓存 stdout/stderr、提供 stdin 写入能力。"""

    def __init__(self, process):
        self.process = process
        self.stdout_chunks = []
        self.stderr_chunks = []
        self.lock = threading.Lock()
        self._start_reader(process.stdout, self.stdout_chunks)
        self._start_reader(process.stderr, self.stderr_chunks)

    def _start_reader(self, stream: Optional[BinaryIO], buffer: List[str]):
        if stream is None:
            return

        def _reader():
            try:
                while True:
                    chunk = stream.readline()
                    if not chunk:
                        break
                    text = decode_bytes(chunk)  # bytes -> str
                    with self.lock:
                        buffer.append(text)
            except Exception:
                pass

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

    def read_output(self, clear=True):
        with self.lock:
            out = "".join(self.stdout_chunks)
            err = "".join(self.stderr_chunks)
            if clear:
                self.stdout_chunks.clear()
                self.stderr_chunks.clear()
        return out, err

    def send_input(self, data, newline=True):
        if self.process.poll() is not None:
            raise RuntimeError(
                f"进程已退出（退出码 {self.process.returncode}），无法再发送输入"
            )
        if self.process.stdin is None:
            raise RuntimeError("该进程没有可用的 stdin 管道")
        s = str(data)
        if newline and not s.endswith("\n"):
            s += "\n"
        try:
            self.process.stdin.write(s.encode('utf-8'))  # str -> bytes
            self.process.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"写入 stdin 失败: {e}")

    def close_input(self):
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except Exception:
                pass

    def is_running(self):
        return self.process.poll() is None


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


# 11. run_command
def tool_run_command(command, cwd=None, timeout=60, env=None, wait=True, shell=None):
    """
    执行 shell 命令并返回其输出。默认在工作目录中运行。

    参数：
        command: 要执行的命令。当 shell=False 时必须是 list/tuple。
        shell:   控制命令的包装方式，默认 None（自动）。
                 - None : Windows 走 PowerShell -EncodedCommand（绕开 cmd 解析），
                          POSIX 走 /bin/sh -c。
                 - True : 强制使用系统默认 shell（Windows 上是 cmd.exe /c），
                          适合确实需要 cmd 内建命令（dir/type/copy 等）的场景。
                 - False: 不做任何 shell 包装，command 必须是 list/tuple，
                          直接交给 subprocess.Popen，跨平台行为最干净。
        wait (bool): 是否等待命令结束并获取输出。
                     若为 False，则命令在后台运行，工具立即返回启动信息，
                     并通过会话 ID（PID）支持后续 send_input / read_output /
                     close_input / kill_background 等交互。
                     默认为 True，保持原有行为。
    """
    # ---------- 规范化 command / shell ----------
    if shell is False:
        if isinstance(command, (str, bytes)):
            raise ValueError(
                "shell=False 时 command 必须是 list 或 tuple，"
                "例如 ['git', 'commit', '-m', 'feat: x']"
            )
        cmd_args = [str(x) for x in command]
        use_shell = False
    elif shell is True:
        if not isinstance(command, str):
            raise ValueError("shell=True 时 command 必须是字符串")
        cmd_args = command
        use_shell = True
    else:  # shell is None -> 自动
        if not isinstance(command, str):
            raise ValueError(
                "自动模式（shell=None）下 command 必须是字符串；"
                "若想直接 exec 参数列表请显式传 shell=False"
            )
        if sys.platform == "win32":
            cmd_args = wrap_powershell(command)
            use_shell = False
        else:
            cmd_args = command
            use_shell = True

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
        pop_kwargs = dict(
            shell=use_shell,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env_vars,
        )
        # 只有后台模式才需要可写 stdin
        if not wait:
            pop_kwargs["stdin"] = subprocess.PIPE

        if sys.platform == "win32":
            pop_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            pop_kwargs["start_new_session"] = True

        process = subprocess.Popen(cmd_args, **pop_kwargs)

        # 如果不等待，则直接返回（不启动定时器，不调用 communicate）
        if not wait:
            # ... 以下与原实现完全一致，保持不变 ...
            if sys.platform == "win32":
                _init_job_object()
                if _job_handle:
                    kernel32 = ctypes.windll.kernel32
                    pid = process.pid
                    desired = 0x0100 | 0x0001 | 0x0400
                    handle = kernel32.OpenProcess(desired, False, pid)
                    if handle:
                        ret = kernel32.AssignProcessToJobObject(_job_handle, handle)
                        kernel32.CloseHandle(handle)
                        if not ret:
                            from ds.logger import LOGGER
                            LOGGER.warn(
                                f"AssignProcessToJobObject 失败 (PID: {pid})，将依赖 atexit 清理"
                            )

            session = _BGSession(process)
            _background_sessions[process.pid] = session
            _background_processes.append(process)

            global _atexit_registered
            if not _atexit_registered:
                atexit.register(_cleanup_background_processes)
                _atexit_registered = True

            time.sleep(0.2)
            return (
                f"后台命令已启动 (PID: {process.pid})。"
                f"可用 send_input / read_output / close_input / kill_background / list_background 与其交互。"
            )

        # 启动超时定时器
        timer = threading.Timer(timeout, force_kill)
        timer.daemon = True
        timer.start()

        stdout_b, stderr_b = process.communicate()
        timer.cancel()

        stdout = decode_bytes(stdout_b or b"")
        stderr = decode_bytes(stderr_b or b"")

        if timed_out.is_set():
            output = stdout + stderr
            raise RuntimeError(
                f"最后输出：\n{truncate(output or '无输出')}\n"
                f"命令执行超时（{timeout} 秒），已被强制终止"
            )

        output = stdout + stderr
        if process.returncode != 0:
            raise RuntimeError(
                f"命令执行失败（退出码 {process.returncode}）：\n{truncate(output or '无输出')}"
            )
        return truncate(output.strip() or "(命令执行成功，无输出)")

    except Exception as e:
        raise RuntimeError(f"命令执行错误: {e}")

    finally:
        if wait and process and process.poll() is None:
            _kill_process_tree(process, process.pid)


# ===== 更新 TOOLS["run_command"] 定义 =====
TOOLS["run_command"] = {
    "description": (
        "执行 shell 命令并返回其输出。默认在工作目录中运行。"
        "shell 参数控制命令的包装方式：默认（不传）时 Windows 走 PowerShell "
        "（-EncodedCommand，绕开 cmd 的引号解析），POSIX 走 /bin/sh -c；"
        "shell=True 强制使用系统默认 shell（Windows 上是 cmd.exe）；"
        "shell=False 则把 command 当作参数列表直接 exec，不做任何 shell 包装。"
        "若设置 wait=False，命令在后台运行，工具立即返回 PID，"
        "后续可用 send_input / read_output / close_input / kill_background 与之交互。"
    ),
    "parameters": {
        "command": {"type": "string", "required": True,
                    "description": "要执行的命令。shell=False 时必须传入字符串数组"},
        "cwd": {"type": "string", "required": False, "description": "命令的工作目录"},
        "timeout": {"type": "number", "required": False,
                    "description": "超时时间（秒），默认 60，仅当 wait=True 时有效"},
        "env": {"type": "object", "required": False, "description": "额外的环境变量（键值对）"},
        "wait": {"type": "boolean", "required": False,
                 "description": "是否等待命令完成并返回输出，默认 True。"
                                "设为 False 时命令后台运行，立即返回 PID。"},
        "shell": {"type": "boolean", "required": False,
                  "description": "命令包装方式。不传=自动（推荐）；"
                                 "True=使用系统默认 shell（Windows 上是 cmd）；"
                                 "False=直接 exec 参数列表（command 需为数组）。"},
    },
    "execute": tool_run_command,
}


# ===== 后台任务交互工具 =====

def tool_send_input(pid, data, newline=True):
    """向指定后台进程的 stdin 发送一行输入。"""
    session = _background_sessions.get(int(pid))
    if not session:
        raise RuntimeError(f"未找到 PID 为 {pid} 的后台会话")
    session.send_input(data, newline=newline)
    return {"success": True, "data": f"已向 PID {pid} 发送输入: {data!r}"}


TOOLS["send_input"] = {
    "description": "向通过 run_command(wait=False) 启动的后台进程发送 stdin 输入（默认追加换行）。",
    "parameters": {
        "pid": {"type": "integer", "required": True, "description": "后台进程 PID"},
        "data": {"type": "string", "required": True, "description": "要写入 stdin 的内容"},
        "newline": {"type": "boolean", "required": False, "description": "是否自动追加换行，默认 True"},
    },
    "execute": tool_send_input,
}


def tool_close_input(pid):
    """关闭后台进程的 stdin（相当于发送 EOF，可让交互式程序退出）。"""
    session = _background_sessions.get(int(pid))
    if not session:
        raise RuntimeError(f"未找到 PID 为 {pid} 的后台会话")
    session.close_input()
    return {"success": True, "data": f"已关闭 PID {pid} 的 stdin"}


TOOLS["close_input"] = {
    "description": "关闭后台进程的 stdin（发送 EOF），常用于结束交互式程序的输入循环。",
    "parameters": {
        "pid": {"type": "integer", "required": True, "description": "后台进程 PID"},
    },
    "execute": tool_close_input,
}


def tool_read_output(pid, clear=True, wait=0.0):
    """读取后台进程截至目前产生的输出。"""
    session = _background_sessions.get(int(pid))
    if not session:
        raise RuntimeError(f"未找到 PID 为 {pid} 的后台会话")
    if wait and wait > 0:
        time.sleep(float(wait))
    out, err = session.read_output(clear=clear)
    combined = (out + err).strip()
    status = "运行中" if session.is_running() else f"已退出（退出码 {session.process.returncode}）"
    header = f"[PID {pid} · {status}]"
    return f"{header}\n{truncate(combined or '(暂无新输出)')}"


TOOLS["read_output"] = {
    "description": "读取后台进程截至目前的 stdout/stderr。默认读取后清空缓存。",
    "parameters": {
        "pid": {"type": "integer", "required": True, "description": "后台进程 PID"},
        "clear": {"type": "boolean", "required": False, "description": "是否清空缓存，默认 True"},
        "wait": {"type": "number", "required": False, "description": "读取前额外等待秒数，默认 0"},
    },
    "execute": tool_read_output,
}


def tool_kill_background(pid):
    """强制终止指定后台进程树。"""
    pid = int(pid)
    session = _background_sessions.get(pid)
    if not session:
        raise RuntimeError(f"未找到 PID 为 {pid} 的后台会话")
    _kill_process_tree(session.process, pid)
    return {"success": True, "data": f"已终止 PID {pid}"}


TOOLS["kill_background"] = {
    "description": "强制终止通过 run_command(wait=False) 启动的后台进程树。",
    "parameters": {
        "pid": {"type": "integer", "required": True, "description": "后台进程 PID"},
    },
    "execute": tool_kill_background,
}


def tool_list_background():
    if not _background_sessions:
        return "(无后台任务)"
    lines = []
    for pid, session in _background_sessions.items():
        p = session.process
        status = "运行中" if p.poll() is None else f"已退出（退出码 {p.returncode}）"
        lines.append(f"PID {pid}: {status}")
    return "\n".join(lines)


TOOLS["list_background"] = {
    "description": "列出当前所有后台任务及其状态。",
    "parameters": {},
    "execute": tool_list_background,
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
            env={**os.environ, "DSA_LOG_FILE": os.environ.get("DSA_LOG_FILE", "")}
        )
        stdout = decode_bytes(result.stdout or b"")
        stderr = decode_bytes(result.stderr or b"")
        output = stdout + "\n" + stderr
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

        # 从返回信息中提取 PID 后，演示发送输入（这里仅作演示）
        # 例如:
        #   print(tool_list_background())
        #   print(tool_read_output(<pid>, wait=1))
        #   print(tool_kill_background(<pid>))

    main()