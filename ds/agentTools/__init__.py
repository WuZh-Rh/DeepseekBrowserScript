#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 02:12
# @Author  : Wu_RH
# @FileName: __init__.py.py

TOOLS = {}


def init_tools():
    from ds.agentTools import file
    from ds.agentTools import qqbot
    from ds.agentTools import task


# ---- 工具描述和调度 ----
def get_tool_descriptions():
    lines = []
    for name, tool in TOOLS.items():
        desc = tool["description"]
        params = tool.get("parameters", {})
        param_lines = []
        for pname, pinfo in params.items():
            required = "，必填" if pinfo.get("required", False) else ""
            desc2 = pinfo.get("description", "")
            param_lines.append(f"    - {pname}（{pinfo.get('type', 'string')}{required}）：{desc2}")
        lines.append(f"### {name}\n  {desc}\n  参数：\n" + "\n".join(param_lines))
    return "\n\n".join(lines)


def execute_tool(name, args):
    tool = TOOLS.get(name)
    if not tool:
        available = ", ".join(TOOLS.keys())
        raise ValueError(f"未知工具：\"{name}\"。可用工具：{available}")
    try:
        return tool["execute"](**args)
    except Exception as e:
        # 捕获异常并重新抛出，让上层处理
        raise RuntimeError(f"工具执行错误: {e}") from e


init_tools()
