#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:55
# @Author  : Wu_RH
# @FileName: agent.py
# src/agent.py
import os
import sys
import subprocess
import traceback
from pathlib import Path
from .config import CONFIG
from .logger import logger
from .browser import DeepSeekBrowser
from ds.agentTools import execute_tool
from .prompt import ConversationManager


class DeepSeekAgent:
    def __init__(self, options=None):
        options = options or {}
        self.browser = DeepSeekBrowser()
        self.conversation = ConversationManager()
        self.options = options
        self._running = False
        self.test_bat_path = options.get('test_bat')
        self.log_file_path = options.get('log_file')
        self.done_test = True

    def init(self):
        self.browser.launch()
        self.browser.new_chat()

    def shutdown(self):
        self.browser.close()

    def _get_working_dir_listing(self):
        cwd = CONFIG["WORKING_DIR"]
        try:
            if sys.platform == 'win32':
                # PowerShell 递归列出文件
                cmd = [
                    'powershell', '-Command',
                    'Get-ChildItem -Recurse -File | Select-Object -First 80 | ForEach-Object { $_.FullName }'
                ]
                result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=5)
            else:
                # Linux/Mac
                cmd = (
                    'find . -maxdepth 3 '
                    '-not -path "*/node_modules/*" '
                    '-not -path "*/.git/*" '
                    '-not -path "*/dist/*" '
                    '-not -path "*/.next/*" '
                    '-not -path "*/build/*" '
                    '-not -name "*.lock" '
                    '| sort | head -80'
                )
                result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=5)
            output = result.stdout.strip()
            return output or "(空目录)"
        except Exception as e:
            logger.error(f"读取工作目录失败: {e}")
            return "(无法读取目录)"

    def _run_test_bat(self):
        if not self.test_bat_path:
            return {"passed": True, "output": "无测试脚本"}
        abs_path = Path(self.test_bat_path)
        if not abs_path.exists():
            return {"passed": False, "output": f"测试脚本不存在: {abs_path}"}
        try:
            env = os.environ.copy()
            env["DSA_LOG_FILE"] = self.log_file_path or ""
            result = subprocess.run(
                str(abs_path),
                shell=True,
                cwd=CONFIG["WORKING_DIR"],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode == 0:
                return {"passed": True, "output": result.stdout.strip() or "(无输出)"}
            else:
                return {"passed": False, "output": (result.stdout + "\n" + result.stderr).strip()}
        except Exception as e:
            return {"passed": False, "output": str(e)}

    def run(self, task):
        self._running = True
        max_iter = CONFIG["MAX_ITERATIONS"]

        # 目录快照
        dir_listing = self._get_working_dir_listing()

        logger.header(f"任务: {task[:80]}{'…' if len(task)>80 else ''}")

        first_msg = self.conversation.build_first_message(task, dir_listing)
        if CONFIG["DEBUG"]:
            logger.dim("--- 第一条消息（已截断）---")
            logger.dim(first_msg[:600] + "...")

        logger.info("正在向 DeepSeek 发送任务...")
        self.browser.send_message(first_msg)

        test_failed = False
        other_tool_called_after_test = False

        for iter_num in range(1, max_iter + 1):
            logger.iteration(iter_num, max_iter)

            try:
                raw_response = self.browser.wait_for_response()
            except Exception as e:
                return {"content": str(e), "completed": False}
            if not raw_response or not raw_response.strip():
                logger.warn("收到空响应 — 正在重试...")
                self.browser.send_message("请继续。如果你在等待输入，请做出最佳判断后继续。")
                continue

            if CONFIG["DEBUG"]:
                logger.dim(f"--- 原始响应（{len(raw_response)} 字符）---")
                logger.dim(raw_response[:400])

            self.conversation.add_assistant_message(raw_response)

            parsed = self.browser.get_latest_tool_calls()

            if parsed["type"] == "tool_call":
                feedback = ""
                for tool in parsed["tools"]:
                    name = tool["name"]
                    args = tool["args"]
                    logger.tool_call(name, args)
                    result_success = True

                    # 连续测试检查
                    if name == "run_test":
                        if test_failed and not other_tool_called_after_test:
                            warning = self.conversation.add_tool_result(
                                "SYSTEM",
                                "⚠️ 测试已失败过了，你尚未调用任何其他工具来修复问题。请先使用其他工具修复代码。",
                                True
                            )
                            self.browser.send_message(warning)
                            feedback = None
                            break

                    try:
                        tool_result = execute_tool(name, args)
                        result = tool_result["data"]
                        result_success = tool_result["success"]
                        if result is None and name == "run_test":
                            return {"content": "", "completed": True}
                        logger.tool_result(result)
                        is_error = False
                    except Exception as e:
                        result = f"错误: {e}"
                        is_error = True
                        logger.tool_result(result, True)

                    # 更新状态
                    if name == "run_test":
                        if result and result.startswith("测试失败"):
                            test_failed = True
                            other_tool_called_after_test = False
                        else:
                            test_failed = False
                            other_tool_called_after_test = False
                    else:
                        other_tool_called_after_test = True

                    feedback += self.conversation.add_tool_result(name, result, is_error)
                    if is_error or (not result_success):
                        break
                if feedback is None:
                    continue
                self.browser.send_message(feedback)
                self.done_test = False
                continue

            elif parsed["type"] == "error":
                logger.warn(f"解析错误: {parsed['message']}")
                recovery = self.conversation.add_tool_result(
                    "SYSTEM",
                    f"解析错误: {parsed['message']}\n\n请重新尝试有效的 JSON 格式工具调用。",
                    True
                )
                self.browser.send_message(recovery)
                continue

            elif parsed["type"] == "final":
                logger.info("AI 试图直接输出最终答案且未调用任何工具。强制要求调用工具继续。")
                force = self.conversation.add_tool_result(
                    "SYSTEM",
                    "❌ 你未调用任何tools，但这不符合工作流程。\n\n"
                    "你必须通过调用工具来完成任务。如果需要退出则直接调用run_test\n"
                    "请立即调用合适的工具继续工作。",
                    True
                )
                self.browser.send_message(force)
                continue

        self._running = False
        warn = f"⚠ 已达到最大迭代次数 ({max_iter})。任务可能未完成。"
        logger.warn(warn)
        return {"content": warn, "completed": False}

    def run_interactive(self):
        logger.header("交互模式 — 输入你的任务，按回车执行")
        logger.info('命令: "exit" 或 "quit" 退出, "new" 开始新对话\n')

        while True:
            try:
                task = input("\n\x1b[96m❯ 任务:\x1b[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not task:
                continue
            if task.lower() in ("exit", "quit", "q"):
                logger.info("正在退出...")
                break
            if task.lower() == "new":
                logger.info("开始新对话...")
                self.browser.new_chat()
                self.conversation = ConversationManager()
                continue

            self.conversation = ConversationManager()
            try:
                self.browser.new_chat()
                self.run(task)
            except Exception as e:
                error_str = traceback.format_exc()
                logger.error(f"任务失败: {e}")
                for error_line in error_str.split("\n"):
                    logger.error(error_line)
