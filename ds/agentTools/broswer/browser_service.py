#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
独立浏览器子进程服务，运行 Playwright 同步 API，
通过 multiprocessing.Queue 与主进程通信。
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

# 修复 asyncio 问题（服务内部不受主进程影响，但仍做清除）
import asyncio
from typing import Optional

try:
    asyncio.set_event_loop(None)
except RuntimeError:
    pass

from playwright.sync_api import sync_playwright, Page, Browser

from ds.config import CONFIG


class BrowserService:
    """在子进程中运行的浏览器服务，单例模式，通过队列响应命令。"""

    def __init__(self, command_queue, result_queue):
        self.command_queue = command_queue
        self.result_queue = result_queue
        self.playwright = None
        self.context = None
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self._initialized = False
        self._custom_js = {}
        self._running = True

    def _launch(self):
        """启动浏览器（同步 API）"""
        if self._initialized:
            return

        self.playwright = sync_playwright().start()
        session_dir = Path(CONFIG["SESSION_DIR"]) / "tools"
        session_dir.mkdir(parents=True, exist_ok=True)

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=CONFIG["HEADLESS"],
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 "
                       "Safari/537.36",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        self.browser = self.context.browser
        self._initialized = True

    def _kill_browser(self):
        """强制终止浏览器进程"""
        if not self.browser:
            return
        try:
            pid = self.browser._impl_obj._connection._transport._proc.pid
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        self.browser = None
        self.context = None
        self.page = None
        self._initialized = False

    def _execute_command(self, cmd, args):
        """执行命令并返回结果"""
        method = getattr(self, f"_cmd_{cmd}", None)
        if method is None:
            return {"error": f"未知命令: {cmd}"}
        try:
            result = method(**args)
            return {"result": result}
        except Exception as e:
            return {"error": f"命令执行错误: {e}", "traceback": traceback.format_exc()}

    # ---------- 命令实现 ----------
    def _cmd_navigate(self, url, timeout=30000):
        self._launch()
        self.page.goto(url, wait_until="networkidle", timeout=timeout)
        return f"已导航到 {url}"

    def _cmd_wait(self, ms=1000):
        self._launch()
        self.page.wait_for_timeout(ms)
        return f"已等待 {ms} 毫秒"

    def _cmd_get_json_snapshot(
        self, max_depth=10, max_children=200, max_nodes=500,
        include_attrs=None, exclude_attrs=None
    ):
        if exclude_attrs is None:
            exclude_attrs = ["style"]
        params = {
            "maxDepth": max_depth,
            "maxChildren": max_children,
            "maxNodesLimit": max_nodes,
            "includeAttrs": include_attrs or [],
            "excludeAttrs": exclude_attrs
        }
        js_path = Path(__file__).parent / "dom_snapshot.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()
        tree_data = self.page.evaluate(js_code, params)
        return json.dumps(tree_data, ensure_ascii=False, sort_keys=False)

    def _cmd_get_html(self):
        self._launch()
        return self.page.content()

    def _cmd_execute_js(self, js_code, timeout=30, args=None):
        self._launch()
        timer = None
        timed_out = False

        def kill():
            nonlocal timed_out
            timed_out = True
            self._kill_browser()

        try:
            timer = threading.Timer(timeout, kill)
            timer.daemon = True
            timer.start()

            # 将 args 转换为可序列化的 Python 对象，传递给 JS
            result = self.page.evaluate(js_code, arg=args)
            timer.cancel()
            return str(result) if result is not None else "(无返回值)"
        except Exception as e:
            if timed_out or "Connection closed" in str(e) or "Target closed" in str(e):
                return f"执行 JS 超时（{timeout} 秒），浏览器已强制终止。"
            else:
                return f"执行 JS 出错: {e}"
        finally:
            if timer:
                timer.cancel()

    def _cmd_save_js(self, name, js_code):
        self._custom_js[name] = js_code
        return f"已保存 JS 代码: {name}"

    def _cmd_run_saved_js(self, name, timeout=30, args=None):
        if name not in self._custom_js:
            return f"未找到名为 '{name}' 的 JS 代码"
        return self._cmd_execute_js(self._custom_js[name], timeout, args)

    def _cmd_click(self, target, by_ref=False):
        self._launch()
        selector = f'[data-ds-ref="{target}"]' if by_ref else target
        try:
            self.page.click(selector, timeout=5000)
            return f"已点击 {target}"
        except Exception as e:
            return f"点击失败: {e}"

    def _cmd_fill(self, target, text, by_ref=False):
        self._launch()
        selector = f'[data-ds-ref="{target}"]' if by_ref else target
        try:
            self.page.fill(selector, text, timeout=5000)
            return f"已填入 '{text}' 到 {target}"
        except Exception as e:
            return f"填充失败: {e}"

    def _cmd_hover(self, target, by_ref=False):
        self._launch()
        selector = f'[data-ds-ref="{target}"]' if by_ref else target
        try:
            self.page.hover(selector, timeout=5000)
            return f"已悬停 {target}"
        except Exception as e:
            return f"悬停失败: {e}"

    def _cmd_scroll(self, x, y):
        self._launch()
        self.page.evaluate(f"window.scrollTo({x}, {y})")
        return f"已滚动到 ({x}, {y})"

    def _cmd_screenshot(self, path=None):
        self._launch()
        if path is None:
            from tempfile import gettempdir
            path = Path(gettempdir()) / f"playwright_screenshot_{int(time.time())}.png"
        self.page.screenshot(path=str(path), full_page=False)
        return str(path)

    def _cmd_get_page_info(self):
        self._launch()
        return {"title": self.page.title(), "url": self.page.url}

    def _cmd_clear_session(self):
        session_dir = Path(CONFIG["SESSION_DIR"]) / "tools"
        self.close()
        if session_dir.exists():
            import shutil
            shutil.rmtree(session_dir)
        self._initialized = False
        return "浏览器会话已清空"

    def _cmd_close(self):
        self.close()
        return "浏览器已关闭"

    def close(self):
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
        self._initialized = False

    def run(self):
        """主循环：处理命令直到收到 'exit'"""
        while self._running:
            try:
                cmd, args = self.command_queue.get(timeout=1)
                if cmd == "exit":
                    self._running = False
                    break
                result = self._execute_command(cmd, args)
                self.result_queue.put(result)
            except Exception:
                # 超时或其他异常，继续
                continue

        self.close()


if __name__ == "__main__":
    # 用于独立调试（不会实际使用）
    print("Browser service entry point.")
