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

from ds.config import CONFIG
from ds.logger import LOGGER
from ds.browser import DeepSeekBrowser
from ds.agentTools import execute_tool
from ds.prompt import ConversationManager
from ds.utils import decode_bytes


def _get_prompt():
    prompt_file = CONFIG["PROMPT_FILE"]
    if not prompt_file.exists():
        prompt_file.touch()
    with open(prompt_file, "r", encoding="utf-8") as f:
        result = f.read()
    open(prompt_file, 'w').close()
    return ("\n" + result) if result else ""


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
        # resume 子命令目标：None 表示不衔接（新建对话）
        # "__latest__" 表示衔接最近一次；数字=索引；其它=标题匹配
        self.resume_target = options.get('resume')
        self._resumed = False

    def init(self):
        self.browser.launch()
        from ds.agentTools import set_browser
        set_browser(self.browser)
        if self.resume_target is not None:
            self.resume_chat(self.resume_target)
            self._resumed = True
        else:
            self.browser.new_chat()

    def resume_chat(self, target):
        """衔接历史对话（切换到已有的某个对话）。

        :param target: "__latest__"/None/"" -> 侧边栏第一条（最近一次对话）
                       纯数字字符串/int         -> 侧边栏索引（0 为最近）
                       其它字符串               -> 对话标题（部分匹配）
        """
        if target is None or target == "" or target == "__latest__":
            self.browser.select_chat_by_index(0)
            LOGGER.info("已衔接最近一次对话")
            return
        t = str(target).strip()
        if t.lstrip("+-").isdigit():
            idx = int(t)
            self.browser.select_chat_by_index(idx)
            LOGGER.info(f"已衔接索引为 {idx} 的历史对话")
        else:
            self.browser.select_chat_by_title(t)
            LOGGER.info(f"已衔接标题包含 '{t}' 的历史对话")

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
            LOGGER.error(f"读取工作目录失败: {e}")
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
                env=env,
            )
            stdout = decode_bytes(result.stdout or b"")
            stderr = decode_bytes(result.stderr or b"")
            if result.returncode == 0:
                return {"passed": True, "output": stdout.strip() or "(无输出)"}
            else:
                return {"passed": False, "output": (stdout + "\n" + stderr).strip()}
        except Exception as e:
            return {"passed": False, "output": str(e)}

    def run(self, task, no_send=False):
        self._running = True
        max_iter = CONFIG["MAX_ITERATIONS"]

        if no_send:
            # resume 且未附带任务：不发送任何消息，直接读页面最后一条助手消息继续
            LOGGER.header("任务: （从页面已有对话继续）")
            LOGGER.info("resume：不发送新消息，直接读取页面最后一条消息继续")
        else:
            LOGGER.header(f"任务: {task[:80]}{'…' if len(task) > 80 else ''}")
            if self._resumed:
                # 衔接历史对话：系统提示词、目录上下文都已在历史里，只发任务本身
                first_msg = task
                self.conversation.messages.append({"role": "user", "content": task})
            else:
                # 仅新建对话时才抓目录快照
                dir_listing = self._get_working_dir_listing()
                first_msg = self.conversation.build_first_message(task, dir_listing)
            if CONFIG["DEBUG"]:
                LOGGER.dim("--- 第一条消息（已截断）---")
                LOGGER.dim(first_msg[:600] + "...")
            LOGGER.info("正在向 DeepSeek 发送任务...")
            self.browser.send_message(first_msg + _get_prompt())

        test_failed = False
        other_tool_called_after_test = False

        for iter_num in range(1, max_iter + 1):
            LOGGER.iteration(iter_num, max_iter)

            if iter_num == 1 and no_send:
                # 不等待新消息，直接读页面已有的最后一条助手消息
                raw_response = self.browser.get_last_assistant_text() or ""
                if not raw_response.strip():
                    LOGGER.warn("页面没有可用的助手消息，无法继续")
                    return {"data": {"content": "no assistant message on page"}, "completed": False}
            else:
                try:
                    raw_response = self.browser.wait_for_response(self.conversation)
                except Exception:
                    return {"data": {"content": traceback.format_exc()}, "completed": False}
            if not raw_response or not raw_response.strip():
                LOGGER.warn("收到空响应 — 正在重试...")
                self.browser.send_message("请继续。如果你在等待输入，请做出最佳判断后继续。" + _get_prompt())
                continue

            if CONFIG["DEBUG"]:
                LOGGER.dim(f"--- 原始响应（{len(raw_response)} 字符）---")
                LOGGER.dim(raw_response[:1000])

            self.conversation.add_assistant_message(raw_response)

            parsed = self.browser.get_latest_tool_calls()

            if parsed["type"] == "tool_call":
                feedback = ""
                for tool in parsed["tools"]:
                    name = tool["name"]
                    args = tool["args"]
                    LOGGER.tool_call(name, args)
                    result_success = True

                    # 连续测试检查
                    if name == "run_test":
                        if test_failed and not other_tool_called_after_test:
                            warning = self.conversation.add_tool_result(
                                "SYSTEM",
                                "⚠️ 测试已失败过了，你尚未调用任何其他工具来修复问题。请先使用其他工具修复代码。",
                                True
                            )
                            warning += _get_prompt()
                            self.browser.send_message(warning)
                            feedback = None
                            break

                    try:
                        tool_result = execute_tool(name, args)
                        result = tool_result["data"]
                        result_success = tool_result["success"]
                        if result_success and name == "run_test":
                            return {"data": {"content": "run_test"}, "completed": True}
                        if result_success and name == "abort_task":
                            return {
                                "data": {"content": "abort_task", "exitcode": int(result)},
                                "completed": True
                            }
                        LOGGER.tool_result(result)
                        is_error = False
                    except Exception as e:
                        result = f"错误: {e}"
                        is_error = True
                        LOGGER.tool_result(result, True)

                    # 更新状态
                    if name == "run_test":
                        if not result_success:
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
                if not feedback:
                    continue
                feedback += _get_prompt()
                self.browser.send_message(feedback)
                self.done_test = False
                continue

            elif parsed["type"] == "error":
                LOGGER.warn(f"解析错误: {parsed['message']}")
                recovery = self.conversation.add_tool_result(
                    "SYSTEM",
                    f"解析错误: {parsed['message']}\n\n请重新尝试有效的 JSON 格式工具调用。",
                    True
                )
                recovery += _get_prompt()
                self.browser.send_message(recovery)
                continue

            elif parsed["type"] == "final":
                LOGGER.info("AI 试图直接输出最终答案且未调用任何工具。强制要求调用工具继续。")
                force = self.conversation.add_tool_result(
                    "SYSTEM",
                    "❌ 你未调用任何tools，但这不符合工作流程。\n\n"
                    "你必须通过调用工具来完成任务。如果需要退出则直接调用run_test\n"
                    "请立即调用合适的工具继续工作。",
                    True
                )
                force += _get_prompt()
                self.browser.send_message(force)
                continue

        self._running = False
        warn = f"⚠ 已达到最大迭代次数 ({max_iter})。任务可能未完成。"
        LOGGER.warn(warn)
        return {"data": {"content": warn}, "completed": False}

    def run_interactive(self):
        LOGGER.header("交互模式 — 输入你的任务，按回车执行")
        LOGGER.info('命令: "exit"/"quit" 退出, "new" 开始新对话, '
                    '"resume [索引|#标题]" 衔接历史对话\n')

        while True:
            try:
                task = input("\n\x1b[96m❯ 任务:\x1b[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not task:
                continue
            if task.lower() in ("exit", "quit", "q"):
                LOGGER.info("正在退出...")
                break
            if task.lower() == "new":
                LOGGER.info("开始新对话...")
                self.browser.new_chat()
                self.conversation = ConversationManager()
                self._resumed = False
                continue

            # resume / continue [索引|#标题] —— 衔接历史对话
            cmd, _, arg = task.partition(" ")
            if cmd.lower() in ("resume", "continue", "r"):
                arg = arg.strip()
                if arg.startswith("#"):
                    arg = arg[1:].strip()
                elif not arg:
                    arg = "__latest__"
                self.conversation = ConversationManager()
                try:
                    self.resume_chat(arg)
                    self._resumed = True
                except Exception as e:
                    LOGGER.error(f"衔接历史对话失败: {e}")
                    self._resumed = False
                continue

            self.conversation = ConversationManager()
            try:
                # 若当前处于衔接历史对话状态，则不要新建对话
                if not self._resumed:
                    self.browser.new_chat()
                self.run(task)
            except Exception as e:
                error_str = traceback.format_exc()
                LOGGER.error(f"任务失败: {e}")
                for error_line in error_str.split("\n"):
                    LOGGER.error(error_line)
