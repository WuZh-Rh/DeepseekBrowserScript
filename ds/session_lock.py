#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/08/24
# @Author  : Wu_RH
# @FileName: session_lock.py
#
# 会话目录锁：防止多个 agent 实例共用同一个 SESSION_DIR 导致浏览器数据冲突。

import os
import sys
import json
import atexit
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    import msvcrt
    _IS_WINDOWS = True
else:
    import fcntl
    _IS_WINDOWS = False


class SessionLockError(RuntimeError):
    """无法获取会话锁时抛出。"""
    pass


def _format_holder_info(info: dict) -> str:
    if not info:
        return "    (未知，可能是上一次异常退出的残留锁)"
    lines = []
    if info.get("pid"):
        lines.append(f"    PID      : {info['pid']}")
    if info.get("host"):
        lines.append(f"    主机     : {info['host']}")
    if info.get("time"):
        lines.append(f"    启动时间 : {info['time']}")
    if info.get("cmd"):
        lines.append(f"    命令行   : {info['cmd']}")
    return "\n".join(lines) if lines else "    (未知)"


class SessionLock:
    """基于文件锁的会话目录互斥锁。

    使用平台原生文件锁（Windows 用 msvcrt，Unix 用 fcntl），
    进程退出（包括崩溃/被 kill）时由内核自动释放，无需手动清理。
    """

    def __init__(self, session_dir):
        self.session_dir = Path(session_dir)
        self.lock_file = self.session_dir / ".session.lock"
        self.info_file = self.session_dir / ".session.lock.info"
        self._fd: Optional[int] = None
        self._acquired = False
        self._atexit_registered = False

    # ---------- 占用者信息 ----------
    def _read_holder_info(self) -> dict:
        try:
            if self.info_file.exists():
                return json.loads(self.info_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _write_holder_info(self):
        info = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "time": datetime.now().isoformat(timespec="seconds"),
            "cmd": " ".join(sys.argv) if sys.argv else "",
        }
        try:
            self.info_file.write_text(
                json.dumps(info, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ---------- 获取 / 释放 ----------
    def acquire(self, timeout: float = 0.0) -> None:
        """尝试获取锁。若被占用则抛 SessionLockError。

        timeout: 等待秒数（0 = 不等待，立即失败）
        """
        if self._acquired:
            return

        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.lock_file), os.O_RDWR | os.O_CREAT, 0o644)

        # Windows 的 msvcrt.locking 需要文件至少 1 字节
        try:
            if os.fstat(self._fd).st_size == 0:
                os.write(self._fd, b"\0")
            os.lseek(self._fd, 0, os.SEEK_SET)
        except OSError:
            pass

        deadline = time.time() + timeout
        while True:
            try:
                if _IS_WINDOWS:
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                # 获取成功
                self._acquired = True
                self._write_holder_info()
                if not self._atexit_registered:
                    atexit.register(self.release)
                    self._atexit_registered = True
                return

            except (OSError, IOError) as e:
                if time.time() >= deadline:
                    holder = self._read_holder_info()
                    try:
                        os.close(self._fd)
                    except Exception:
                        pass
                    self._fd = None
                    raise SessionLockError(
                        f"❌ 会话目录已被占用，无法启动：\n"
                        f"   目录 : {self.session_dir}\n"
                        f"   占用者：\n{_format_holder_info(holder)}\n"
                        f"\n"
                        f"   请等待该进程结束后重试，或者使用参数 --session-dir <其它名字> 指定一个独立的会话目录。"
                    ) from e
                time.sleep(0.5)

    def release(self) -> None:
        if not self._acquired or self._fd is None:
            return
        try:
            try:
                if _IS_WINDOWS:
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception:
                pass
        finally:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
            self._acquired = False
            # 只删 info，不删 lock 文件本身（避免和"打开后再删除"的竞态）
            try:
                if self.info_file.exists():
                    self.info_file.unlink()
            except Exception:
                pass

    @property
    def acquired(self) -> bool:
        return self._acquired

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


# ---------- 全局单例 ----------
_GLOBAL_LOCK: Optional[SessionLock] = None


def acquire_session_lock(session_dir, timeout: float = 0.0) -> SessionLock:
    """获取指定会话目录的锁；同进程重复调用直接返回已有锁。"""
    global _GLOBAL_LOCK
    if _GLOBAL_LOCK is not None and _GLOBAL_LOCK.acquired:
        return _GLOBAL_LOCK
    lock = SessionLock(session_dir)
    lock.acquire(timeout=timeout)
    _GLOBAL_LOCK = lock
    return lock


def get_session_lock() -> Optional[SessionLock]:
    return _GLOBAL_LOCK


def release_session_lock() -> None:
    global _GLOBAL_LOCK
    if _GLOBAL_LOCK is not None:
        _GLOBAL_LOCK.release()
        _GLOBAL_LOCK = None