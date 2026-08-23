#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 02:12
# @Author  : Wu_RH
# @FileName: __init__.py.py

from ds.config import CONFIG

TOOLS = {}


def init_tools():
    from ds.agentTools import file
    from ds.agentTools import qqbot
    from ds.agentTools import task
    from ds.agentTools.broswer import browser


# ---- 工具描述和调度 ----
def get_tool_descriptions():
    lines = []
    allow_tools = CONFIG.get("allow_tools", [])
    for name, tool in TOOLS.items():
        if name not in allow_tools:
            continue
        desc = tool["description"]
        params = tool.get("parameters", {})
        param_lines = []
        for pname, pinfo in params.items():
            required = "，必填" if pinfo.get("required", False) else ""
            desc2 = pinfo.get("description", "")
            param_lines.append(f"    - {pname}（{pinfo.get('type', 'string')}{required}）：{desc2}")
        lines.append(f"### {name}\n  {desc}\n  参数：\n" + "\n".join(param_lines))
    return "\n\n".join(lines)


def execute_tool(name, args) -> dict[str, str]:
    allow_tools = CONFIG.get("allow_tools", [])
    if allow_tools and name not in allow_tools:
        available = ", ".join([i for i in TOOLS.keys() if i in allow_tools])
        raise ValueError(f"未知工具：\"{name}\", 可用工具: {available}")
    tool = TOOLS.get(name)
    if not tool:
        available = ", ".join([i for i in TOOLS.keys() if i in allow_tools])
        raise ValueError(f"未知工具: \"{name}\", 可用工具: {available}")
    try:
        result = tool["execute"](**args)
        if isinstance(result, dict):
            result["success"] = result.get("success", True)
            result["data"] = result.get("data", "(工具无返回内容)")
            return result
        if isinstance(result, str):
            return {"data": result, "success": True}
        from ds.logger import LOGGER
        LOGGER.warn(f"工具[{name}]({args})返回了非法返回值(type:{type(result)}) 将其自动转为str: {str(result)}")
        return {"data": str(result), "success": True}
    except Exception as e:
        # 捕获异常并重新抛出，让上层处理
        raise RuntimeError(f"工具执行错误: {e}") from e
