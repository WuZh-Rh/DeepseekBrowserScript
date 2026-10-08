#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/10/09 00:31
# @Author  : Wu_RH
# @FileName: utils.py.py

import base64
import os
import shutil
import stat
import tempfile

# 按优先级排列的候选编码。前面的匹配上了就不再看后面的。
_DECODE_CANDIDATES = (
    'utf-8',
    'gbk',
    'utf-16-le',
    'utf-16-be',
    'utf-16',
    'big5',
    'shift_jis',
    'latin-1',
)


def decode_line(line: bytes) -> str:
    if not line:
        return ""
    for enc in _DECODE_CANDIDATES:
        try:
            return line.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 全部失败，用替换字符最少的那个
    best = None
    best_bad = None
    for enc in _DECODE_CANDIDATES:
        try:
            s = line.decode(enc, errors='replace')
        except LookupError:
            continue
        bad = s.count('\ufffd')
        if best is None or bad < best_bad:
            best, best_bad = s, bad
            if bad == 0:
                break
    return best if best is not None else line.decode('utf-8', errors='replace')


def decode_bytes(data: bytes) -> str:
    if not data:
        return ""
    # BOM 优先
    if data.startswith(b'\xef\xbb\xbf'):
        return data[3:].decode('utf-8', errors='replace')
    if data.startswith(b'\xff\xfe'):
        return data[2:].decode('utf-16-le', errors='replace')
    if data.startswith(b'\xfe\xff'):
        return data[2:].decode('utf-16-be', errors='replace')
    # 整段尝试
    for enc in _DECODE_CANDIDATES:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 逐行兜底
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
# ==================== 通用 ssh 执行 ====================


_OS_CACHE = {}


def _make_askpass_script(password: str) -> str:
    """生成临时 askpass 脚本，把密码通过 SSH_ASKPASS 机制喂给 ssh。

    Windows 生成 .cmd（cmd 可执行），POSIX 生成 .sh（chmod +x）。
    脚本本身不含明文密码，只从环境变量 SSH_ASKPASS_PW 读取。
    调用方负责删除。
    """
    if os.name == "nt":
        fd, path = tempfile.mkstemp(suffix=".cmd", prefix="askpass_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("@echo off\r\necho %SSH_ASKPASS_PW%\r\n")
    else:
        fd, path = tempfile.mkstemp(suffix=".sh", prefix="askpass_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nprintf '%s\\n' \"$SSH_ASKPASS_PW\"\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def _exec_capture(args, env, timeout):
    """跑子进程，返回 {exit_code, stdout, stderr}；超时抛 RuntimeError。"""
    import subprocess
    try:
        p = subprocess.run(args, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ssh 执行超时（{timeout}s）")
    except FileNotFoundError as e:
        raise RuntimeError(f"找不到命令 {args[0]}: {e}")
    return {
        "exit_code": p.returncode,
        "stdout": decode_bytes(p.stdout or b""),
        "stderr": decode_bytes(p.stderr or b""),
    }


def _build_remote_cmd(script: str, remote: str) -> str:
    """按远端 OS 类型把脚本封装成一条远程命令行（脚本经 base64 传输）。"""
    if remote == "windows":
        wrapped = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script
        b64 = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
        return ("powershell -NoProfile -NonInteractive "
                "-ExecutionPolicy Bypass -EncodedCommand " + b64)
    if remote == "posix":
        # base64 字符集只有 [A-Za-z0-9+/=]，单引号包裹绝对安全，
        # 远端任何 shell（bash/sh）都不会误解析脚本内容。
        b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
        return "printf '%s' '" + b64 + "' | base64 -d | sh"
    raise ValueError(f"未知 remote 类型: {remote}")


def _ssh_invoke(host, remote_cmd, user, password, port, key_filename,
                extra_opts, connect_timeout, timeout):
    """执行一条远程命令，自动选择认证方式。返回 _exec_capture 的结果。"""
    env = dict(os.environ)
    cleanup = None
    target = f"{user}@{host}" if user else host

    if password:
        # 1) plink（PuTTY，-pw 直给密码，最稳）
        plink = shutil.which("plink") or shutil.which("plink.exe")
        if plink:
            args = [plink, "-ssh", "-batch", "-pw", password]
            if port:
                args += ["-P", str(port)]
            if key_filename:
                args += ["-i", key_filename]
            args += [target, remote_cmd]
            return _exec_capture(args, env, timeout)

        # 2) sshpass（Linux/msys）
        sshpass = shutil.which("sshpass")
        if sshpass:
            args = [sshpass, "-p", password, "ssh",
                    "-o", f"ConnectTimeout={connect_timeout}"]
            if port:
                args += ["-p", str(port)]
            if key_filename:
                args += ["-i", key_filename]
            args += extra_opts or []
            args += [target, remote_cmd]
            return _exec_capture(args, env, timeout)

        # 3) SSH_ASKPASS（原生 ssh，无需装东西）
        cleanup = _make_askpass_script(password)
        env["SSH_ASKPASS"] = cleanup
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env["SSH_ASKPASS_PW"] = password
        env["DISPLAY"] = env.get("DISPLAY", ":0")

    args = ["ssh", "-o", f"ConnectTimeout={connect_timeout}",
            "-o", "ServerAliveInterval=5"]
    if not password:
        args += ["-o", "BatchMode=yes"]
    if port:
        args += ["-p", str(port)]
    if key_filename:
        args += ["-i", key_filename]
    args += extra_opts or []
    args += [target, remote_cmd]

    try:
        return _exec_capture(args, env, timeout)
    finally:
        if cleanup and os.path.exists(cleanup):
            try:
                os.remove(cleanup)
            except OSError:
                pass


def _detect_remote_os(host, user, password, port, key_filename, connect_timeout):
    """探测远端是 windows 还是 posix，结果缓存。"""
    key = (host, user, port)
    if key in _OS_CACHE:
        return _OS_CACHE[key]

    # `echo ... & uname -s`：cmd 和 sh 都支持 & 顺序执行。
    # POSIX 会输出 Linux/Darwin/BSD；Windows cmd 的 uname 会报错到 stderr，
    # stdout 只剩 __DSPROBE__。
    probe = "echo __DSPROBE__ & uname -s"
    r = _ssh_invoke(host, probe, user, password, port, key_filename,
                    None, connect_timeout, 30)
    out = (r["stdout"] + " " + r["stderr"]).lower()
    if any(x in out for x in ("linux", "darwin", "bsd", "sunos", "aix")):
        os_type = "posix"
    elif r["stdout"].strip() and "__dsprobe__" in out:
        # 只回了 __DSPROBE__，没有 uname 结果 → Windows
        os_type = "windows"
    else:
        os_type = "posix"  # 兜底
    _OS_CACHE[key] = os_type
    return os_type


def run_ssh_script(
    host: str,
    script: str = None,
    script_windows: str = None,
    script_posix: str = None,
    remote: str = "auto",
    user: str = None,
    password: str = None,
    port: int = None,
    key_filename: str = None,
    extra_opts: list = None,
    timeout: int = 120,
    connect_timeout: int = 20,
):
    """在任意远程主机（Windows / POSIX）执行脚本，返回 {exit_code, stdout, stderr}。

    脚本选择规则（三者至少给一个）：
      * 给了 script_windows / script_posix -> 探测远端 OS 后自动选对应那套，
        调用方完全不用关心对面是 Windows 还是 Linux。
      * 只给了 script -> 按 remote 处理：
          - remote="windows" -> script 当 PowerShell 源码
          - remote="posix"   -> script 当 sh 源码
          - remote="auto"    -> 探测后，脚本按探测结果封装

    - host: ~/.ssh/config 别名，或 ip / user@ip
    - 认证自动降级：plink -pw / sshpass -p / SSH_ASKPASS / 原生密钥
    """
    # ---- 决定 remote 类型 ----
    if remote == "auto":
        remote = _detect_remote_os(host, user, password, port,
                                   key_filename, connect_timeout)
    elif remote in ("linux", "unix", "sh", "bash", "mac", "macos", "darwin"):
        remote = "posix"
    elif remote in ("win", "powershell", "pwsh"):
        remote = "windows"
    if remote not in ("windows", "posix"):
        raise ValueError(f"未知 remote 类型: {remote}")

    # ---- 决定用哪套脚本 ----
    if remote == "windows":
        chosen = script_windows if script_windows is not None else script
    else:
        chosen = script_posix if script_posix is not None else script

    if chosen is None:
        raise ValueError(
            f"远端是 {remote}，但没有提供对应脚本"
            f"（需要 script_{remote} 或通用 script）"
        )

    remote_cmd = _build_remote_cmd(chosen, remote)
    return _ssh_invoke(host, remote_cmd, user, password, port,
                       key_filename, extra_opts, connect_timeout, timeout)
