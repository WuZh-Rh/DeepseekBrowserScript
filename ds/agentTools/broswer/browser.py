#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/08/21
# @Author  : Wu_RH
# @FileName: browser.py

import json
from typing import Optional

from ds.agentTools import TOOLS
from ds.agentTools.broswer.browser_client import BrowserClient

# 创建全局客户端实例
_CLIENT: Optional[BrowserClient] = None


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        from ds.agentTools.broswer.browser_client import BrowserClient
        _CLIENT = BrowserClient()
    return _CLIENT


# ---------- 工具函数（保持不变，仅调用 _CLIENT 方法） ----------
def tool_browser_get_json_snapshot(
    max_depth=10, max_children=200, max_nodes=500,
    include_attrs=None, exclude_attrs=None
):
    if exclude_attrs is None:
        exclude_attrs = ["style"]  # 默认排除 style
    return _get_client().get_json_snapshot(
        max_depth, max_children, max_nodes,
        include_attrs or [], exclude_attrs
    )


def tool_browser_get_html():
    return _get_client().get_html()


def tool_browser_navigate(url, timeout=30000):
    return _get_client().navigate(url, timeout)


def tool_browser_click(target, by_ref=False):
    return _get_client().click(target, by_ref)


def tool_browser_fill(target, text, by_ref=False):
    return _get_client().fill(target, text, by_ref)


def tool_browser_hover(target, by_ref=False):
    return _get_client().hover(target, by_ref)


def tool_browser_scroll(x, y):
    return _get_client().scroll(x, y)


def tool_browser_screenshot(path=None):
    return _get_client().screenshot(path)


def tool_browser_get_page_info():
    return json.dumps(_get_client().get_page_info(), ensure_ascii=False)


def tool_browser_execute_js(js_code, save_as=None, timeout=30, args=None):
    result = _get_client().execute_js(js_code, timeout, args)
    if save_as:
        _get_client().save_js(save_as, js_code)
    return result


def tool_browser_run_saved_js(name, timeout=30, args=None):
    return _get_client().run_saved_js(name, timeout, args)


def tool_browser_clear_session():
    return _get_client().clear_session()


def tool_browser_wait(ms):
    return _get_client().wait_for_timeout(ms)


def tool_browser_new_page(url=None):
    """创建新标签页，可指定 URL。返回新页面 ID。"""
    result = _get_client().new_page(url)
    return json.dumps(result, ensure_ascii=False)


def tool_browser_close_page(page_id):
    """关闭指定 ID 的标签页。"""
    result = _get_client().close_page(page_id)
    return json.dumps(result, ensure_ascii=False)


def tool_browser_switch_page(page_id):
    """切换到指定 ID 的标签页。"""
    result = _get_client().switch_page(page_id)
    return json.dumps(result, ensure_ascii=False)


def tool_browser_list_pages():
    """列出所有打开的标签页及其信息。"""
    result = _get_client().list_pages()
    return json.dumps(result, ensure_ascii=False)


TOOLS["browser_navigate"] = {
    "description": "导航到指定 URL。",
    "parameters": {
        "url": {"type": "string", "required": True, "description": "填入指定的url 将会导航至指定位置"},
        "timeout": {"type": "number", "required": False, "default": 30000, "description": "超时时间(ms) 默认30000ms"},
    },
    "execute": tool_browser_navigate,
}

TOOLS["browser_execute_js"] = {
    "description": "在浏览器中执行自定义 JavaScript 代码，并返回结果。可保存为可复用脚本。(使用playwright的Page.evaluate实现)",
    "parameters": {
        "js_code": {"type": "string", "required": True, "description": "要执行的 JavaScript 代码"},
        "save_as": {
            "type": "string", "required": False,
            "description": "可选，保存此脚本的名称(后续可使用browser_run_saved_js来调用)"
        },
        "timeout": {"type": "number", "required": False, "description": "超时时间（秒），默认 30"},
        "args": {"type": "object", "required": False,
                 "description": "传递给 JS 代码的参数对象，可在 JS 中通过 arguments[0] 或函数形参获取"},
    },
    "execute": tool_browser_execute_js,
}

TOOLS["browser_run_saved_js"] = {
    "description": "运行之前取了别名的 JavaScript 代码（按名称调用）。",
    "parameters": {
        "name": {"type": "string", "required": True, "description": "之前browser_execute_js保存的别名"},
        "timeout": {"type": "number", "required": False, "description": "超时时间（秒），默认 30"},
        "args": {"type": "object", "required": False,
                 "description": "传递给 JS 代码的参数对象，可在 JS 中通过 arguments[0] 获取"},
    },
    "execute": tool_browser_run_saved_js,
}

TOOLS["browser_json_snapshot"] = {
    "description": (
        "获取当前页面的 DOM 树 JSON 快照，用于结构化分析页面结构。"
        "支持属性过滤：传入 include_attrs 则只保留指定属性（白名单），否则按 exclude_attrs 排除（默认排除 style）。"
        "属性名支持通配符 *，如 'on*' 匹配所有 on 开头属性。"
    ),
    "parameters": {
        "max_depth": {"type": "number", "required": False, "description": "最大遍历深度，默认 10"},
        "max_children": {"type": "number", "required": False, "description": "每层最大子节点数，默认 200"},
        "max_nodes": {"type": "number", "required": False, "description": "总节点数上限，默认 500"},
        "include_attrs": {"type": "array", "items": {"type": "string"}, "required": False,
                          "description": "白名单属性列表，非空时忽略黑名单"},
        "exclude_attrs": {"type": "array", "items": {"type": "string"}, "required": False,
                          "description": "黑名单属性列表，默认 ['style']"},
    },
    "execute": tool_browser_get_json_snapshot,
}

TOOLS["browser_get_html"] = {
    "description": "获取当前页面的完整 HTML 源码（用于调试或备用）。",
    "parameters": {},
    "execute": tool_browser_get_html,
}

TOOLS["browser_clear_session"] = {
    "description": "清空当前浏览器会话（删除所有持久化数据：cookies、localStorage、sessionStorage 等），下次调用浏览器工具时会创建全新的会话环境。",
    "parameters": {},
    "execute": tool_browser_clear_session,
}

TOOLS["browser_click"] = {
    "description": "点击页面元素。可通过 CSS 选择器或 ref（如 E1）定位。",
    "parameters": {
        "target": {"type": "string", "required": True, "description": "CSS 选择器 或 ref 编号（如 'E1'）"},
        "by_ref": {"type": "boolean", "required": False,
                   "description": "设为 true 表示 target 是 ref 编号，否则视为 CSS 选择器。默认 false"},
    },
    "execute": tool_browser_click,
}

TOOLS["browser_fill"] = {
    "description": "向输入框填充文本。",
    "parameters": {
        "target": {"type": "string", "required": True, "description": "CSS 选择器 或 ref 编号"},
        "text": {"type": "string", "required": True, "description": "要填入的文本"},
        "by_ref": {"type": "boolean", "required": False, "description": "是否按 ref 定位"},
    },
    "execute": tool_browser_fill,
}

TOOLS["browser_hover"] = {
    "description": "悬停到指定元素。",
    "parameters": {
        "target": {"type": "string", "required": True, "description": "CSS 选择器 或 ref 编号"},
        "by_ref": {"type": "boolean", "required": False, "description": "是否按 ref 定位"},
    },
    "execute": tool_browser_hover,
}

TOOLS["browser_scroll"] = {
    "description": "滚动页面到指定坐标（相对于文档左上角）。",
    "parameters": {
        "x": {"type": "number", "required": True, "description": "水平滚动像素"},
        "y": {"type": "number", "required": True, "description": "垂直滚动像素"},
    },
    "execute": tool_browser_scroll,
}

# TOOLS["browser_screenshot"] = {
#     "description": "截取当前页面截图，返回图片保存路径。",
#     "parameters": {
#         "path": {"type": "string", "required": False, "description": "保存路径，不指定则自动生成临时文件"},
#     },
#     "execute": tool_browser_screenshot,
# }

TOOLS["browser_get_page_info"] = {
    "description": "获取当前页面的标题和 URL。",
    "parameters": {},
    "execute": tool_browser_get_page_info,
}

TOOLS["browser_new_page"] = {
    "description": "打开一个新标签页，并可选择导航到指定 URL。返回新页面的 ID。",
    "parameters": {
        "url": {"type": "string", "required": False, "description": "要导航的 URL（可选）"}
    },
    "execute": tool_browser_new_page,
}

TOOLS["browser_close_page"] = {
    "description": "关闭指定的标签页（通过页面 ID）。注意不能关闭最后一个页面。",
    "parameters": {
        "page_id": {"type": "integer", "required": True, "description": "要关闭的页面 ID"}
    },
    "execute": tool_browser_close_page,
}

TOOLS["browser_switch_page"] = {
    "description": "切换到指定 ID 的标签页，后续浏览器操作将在该页面上执行。",
    "parameters": {
        "page_id": {"type": "integer", "required": True, "description": "目标页面 ID"}
    },
    "execute": tool_browser_switch_page,
}

TOOLS["browser_list_pages"] = {
    "description": "列出当前所有打开的标签页，包含每个页面的 ID、标题和 URL。",
    "parameters": {},
    "execute": tool_browser_list_pages,
}
