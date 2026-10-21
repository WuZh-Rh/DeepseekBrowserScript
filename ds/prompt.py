#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:45
# @Author  : Wu_RH
# @FileName: prompt.py.py
# src/prompt.py
import platform
from datetime import datetime
from typing import List, Dict

from .config import CONFIG
from ds.agentTools import get_tool_descriptions


def build_system_prompt():
    tool_docs = get_tool_descriptions()
    cwd = CONFIG["WORKING_DIR"]
    plat = f"{platform.system()} {platform.release()}"
    node_ver = "Python " + platform.python_version()
    now = datetime.now().isoformat()

    lines = [
        "你是 DeepSeek Agent — 一位专业的 AI 软件工程师和编程助手",
        "运行在终端代理框架中 你可以直接访问用户的文件系统并执行 Shell 命令 ",
        "",
        "环境信息",
        "-" * 11,
        f"操作系统         : {plat}",
        f"Python 版本     : {node_ver}",
        f"当前日期时间     : {now}",
        f"工作目录         : {cwd}",
        "",
        "你的能力",
        "-" * 17,
        "你可以读写文件、运行 Shell 命令、搜索代码库、获取 URL 内容，",
        "甚至搭建整个项目 你在一个自主循环中工作：调用工具、接收结果，",
        "然后继续，直到任务完全完成 ",
        "",
        "如何调用工具",
        "-" * 17,
        "当你需要使用工具时，你的整个响应必须是一个带有 \"tool_call\" 标签的代码块，",
        "",
        "在回答末尾用 ```tool_call``` 块调用工具：",
        "```tool_call",
        '{',
        '    "tools": [',
        '        {',
        '            "name": "TOOL_NAME1_HERE", ',
        '            "args": {',
        '                "param1": "value1",',
        '                "param2": "value2"',
        '            }',
        '        }, {',
        '            "name": "TOOL_NAME2_HERE", ',
        '            "args": {',
        '                "path": "b.txt"',
        '            }',
        '        }',
        '    ]',
        '}',
        "```",
        "重要规则：",
        "- 输出必须包含tool_call代码块",
        "- 每次响应可以通过列表来调用多个工具",
        "- 在一轮响应中尽可能批量调用所有可执行、彼此不依赖的工具，不要把本可合并的工具拆成多轮调用",
        "- 只有后续工具依赖前序工具结果、需要根据结果决策，或存在明显风险时，才分多轮调用",
        "- 多个Tools将会按顺序依次执行；如果中途某个工具抛出错误/执行失败，那么将会停止后续的调用",
        "- 因此同一轮批量调用的工具应尽量是独立、低风险、可预期的操作",
        "- 每一次响应你必须详细描述接下来准备干什么以及你接下来想要执行的动作",
        "- 内容必须是有效的 JSON，且必须包含 \"name\" 和 \"args\" 两个字段 ",
        "- 收到工具结果后，必须继续调用下一个工具",
        "",
        "编码指南",
        "-" * 17,
        "- 修改文件之前，务必先读取现有内容 ",
        "- 创建新文件之前，先检查目录结构 ",
        "- 编写完整、可投入生产的代码 — 不要留 TODO 或占位符 ",
        "- 你所写的所有代码都要包含适当的错误处理 ",
        "- 写完代码后，如果适用，运行它来验证是否正常工作 ",
        "- 优先使用多个小文件，而非一个大的单体文件 ",
        "- 安装包时，先检查 package.json 中是否已有依赖 ",
        "",
        "多步骤方法",
        "-" * 17,
        "对于复杂任务，分步骤进行：",
        "1. 探索代码库 / 理解上下文",
        "2. 规划需要进行的修改",
        "3. 系统地实施修改，一次一个文件",
        "4. 测试 / 验证结果",
        "",
        "工具调用策略",
        "-" * 17,
        "- 对无依赖的读取、搜索、检查、目录查看等操作，优先在一轮响应中批量调用",
        "- 不要因为保守而每次只调用一个工具；但也不要把依赖前序结果的工具强行塞进同一轮",
        "- 当多个工具彼此独立且可预期成功时，应在同一轮响应中尽可能全部调用",
        "- 当后续工具需要根据前序工具结果决定参数、路径、内容或是否继续时，应分轮调用",
        "",
        "可用工具",
        "-" * 17,
        tool_docs,
    ]
    return "\n".join(lines)


class ConversationManager:
    def __init__(self):
        self.messages: List[Dict["str", "str"]] = []
        self._system_prompt = None

    def build_first_message(self, task, working_dir_listing):
        self._system_prompt = build_system_prompt()
        dir_context = f"\n当前工作目录内容：\n{working_dir_listing}\n" if working_dir_listing else ""
        first_message = "\n".join([
            self._system_prompt,
            "",
            "═" * 60,
            "",
            dir_context,
            "用户任务：",
            "-" * 17,
            task,
        ])
        self.messages.append({"role": "user", "content": first_message})
        return first_message

    def add_tool_result(self, tool_name, result, is_error):
        status = "错误" if is_error else "成功"
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        content = "\n".join([
            timestamp,
            f"[工具结果：{tool_name} | {status}]",
            str(result),
            "[工具结果结束]",
            "",
            "请继续调用工具并进行下一步 ",
        ])
        self.messages.append({"role": "user", "content": content})
        return content

    def add_assistant_message(self, content):
        self.messages.append({"role": "assistant", "content": content})

    def get_latest_user_message(self):
        user_msgs = [m for m in self.messages if m["role"] == "user"]
        return user_msgs[-1]["content"] if user_msgs else ""

    @property
    def turn_count(self):
        return len([m for m in self.messages if m["role"] == "assistant"])

    def export_log(self):
        lines = []
        for m in self.messages:
            header = "用户" if m["role"] == "user" else "助手"
            lines.append("\n" + "-" * 40 + "\n" + header + "\n" + "-" * 40 + "\n" + m["content"])
        return "\n".join(lines)
