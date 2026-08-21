#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
浏览器客户端：通过队列与子进程服务通信，提供与浏览器交互的同步接口。
"""

import multiprocessing
import time
from typing import Any, Dict, Optional


def _start_service(self):
    if self._started:
        return

    import multiprocessing
    # 如果当前进程不是主进程（即已经在子进程中），则不再启动子进程
    if multiprocessing.current_process().name != 'MainProcess':
        self._started = True
        return

    self.process = multiprocessing.Process(
        target=_run_browser_service,
        args=(self.command_queue, self.result_queue),
        daemon=True
    )
    self.process.start()
    self._started = True
    time.sleep(0.5)  # 等待服务就绪


def _run_browser_service(cmd_queue, result_queue):
    """模块级函数，作为子进程入口（可 pickle）"""
    from ds.agentTools.broswer.browser_service import BrowserService
    service = BrowserService(cmd_queue, result_queue)
    service.run()


class BrowserClient:
    """客户端代理，向子进程服务发送命令并等待响应。"""

    def __init__(self, start_immediately=False):
        self.command_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        self.process = None
        self._started = False
        if start_immediately:
            self._start_service()

    def _start_service(self):
        """启动子进程服务"""
        if self._started:
            return
        self.process = multiprocessing.Process(
            target=_run_browser_service,
            args=(self.command_queue, self.result_queue),
            daemon=True
        )
        self.process.start()
        self._started = True
        # 等待服务就绪（简单等待）
        time.sleep(0.5)

    def _ensure_started(self):
        """确保服务已启动，若未启动则启动"""
        if not self._started:
            self._start_service()

    def _send_command(self, cmd: str, args: Optional[Dict] = None) -> Any:
        """发送命令并等待结果"""
        self._ensure_started()
        if args is None:
            args = {}
        self.command_queue.put((cmd, args))
        try:
            result = self.result_queue.get(timeout=60)
            if "error" in result:
                raise RuntimeError(result["error"])
            return result["result"]
        except multiprocessing.queues.Empty:
            raise TimeoutError(f"命令 {cmd} 执行超时（60秒）")

    # ---------- 对外接口 ----------
    def navigate(self, url, timeout=30000):
        return self._send_command("navigate", {"url": url, "timeout": timeout})

    def wait_for_timeout(self, ms=1000):
        return self._send_command("wait", {"ms": ms})

    def get_json_snapshot(self, max_depth=50, max_children=30, max_nodes=300):
        return self._send_command("get_json_snapshot", {
            "max_depth": max_depth,
            "max_children": max_children,
            "max_nodes": max_nodes
        })

    def get_html(self):
        return self._send_command("get_html", {})

    def execute_js(self, js_code, timeout=30):
        return self._send_command("execute_js", {"js_code": js_code, "timeout": timeout})

    def save_js(self, name, js_code):
        return self._send_command("save_js", {"name": name, "js_code": js_code})

    def run_saved_js(self, name, timeout=30):
        return self._send_command("run_saved_js", {"name": name, "timeout": timeout})

    def click(self, target, by_ref=False):
        return self._send_command("click", {"target": target, "by_ref": by_ref})

    def fill(self, target, text, by_ref=False):
        return self._send_command("fill", {"target": target, "text": text, "by_ref": by_ref})

    def hover(self, target, by_ref=False):
        return self._send_command("hover", {"target": target, "by_ref": by_ref})

    def scroll(self, x, y):
        return self._send_command("scroll", {"x": x, "y": y})

    def screenshot(self, path=None):
        return self._send_command("screenshot", {"path": path})

    def get_page_info(self):
        return self._send_command("get_page_info", {})

    def clear_session(self):
        return self._send_command("clear_session", {})

    def close(self):
        try:
            self._send_command("close", {})
        except:
            pass
        self.command_queue.put(("exit", {}))
        if self.process and self.process.is_alive():
            self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join()