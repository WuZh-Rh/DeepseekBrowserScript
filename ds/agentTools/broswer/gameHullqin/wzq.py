#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/08/22 22:26
# @Author  : Wu_RH
# @FileName: wzq.py

import json
import re
from typing import Dict, Any, Optional, Tuple, List

from ds.agentTools import TOOLS
from ds.agentTools.broswer.browser import (
    tool_browser_get_page_info,
    tool_browser_get_json_snapshot,
    tool_browser_execute_js,
)

URL = "https://game.hullqin.cn/wzq"
BOARD_SIZE = 15
COL_MAP = {chr(ord('A') + i): i for i in range(BOARD_SIZE)}  # A-O
ROW_MAP = {str(i + 1): i for i in range(BOARD_SIZE)}  # 1-15


def _check_game():
    page_info = eval(tool_browser_get_page_info())
    page_url = page_info["url"]
    return (
        page_url.startswith(URL) and
        (len(page_url) != len(URL))
    )


def _parse_pos(pos: str) -> Optional[Tuple[int, int]]:
    pos = pos.strip().upper()
    match = re.match(r'^([A-O])([1-9]|1[0-5])$', pos)
    if match:
        col = COL_MAP[match.group(1)]
        row = ROW_MAP[match.group(2)]
        return row, col
    if ',' in pos:
        parts = pos.split(',')
        if len(parts) == 2:
            try:
                row = int(parts[0]) - 1
                col = int(parts[1]) - 1
                if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                    return row, col
            except ValueError:
                pass
    return None


def _find_node(node, tag=None, attrs=None):
    """递归查找第一个匹配的节点"""
    if not isinstance(node, dict):
        return None
    if tag and node.get('tag') != tag:
        pass
    else:
        if attrs:
            match = True
            for k, v in attrs.items():
                if node.get(k) != v:
                    match = False
                    break
            if match:
                return node
    for child in node.get('children', []):
        result = _find_node(child, tag, attrs)
        if result:
            return result
    return None


def _find_all_nodes(node, tag=None, attrs=None):
    """递归查找所有匹配的节点，返回列表"""
    results = []
    if not isinstance(node, dict):
        return results
    if tag and node.get('tag') != tag:
        pass
    else:
        if attrs:
            match = True
            for k, v in attrs.items():
                if node.get(k) != v:
                    match = False
                    break
            if match:
                results.append(node)
        else:
            results.append(node)
    for child in node.get('children', []):
        results.extend(_find_all_nodes(child, tag, attrs))
    return results


def _extract_text(node):
    """提取节点的文本（合并所有文本子节点）"""
    if not isinstance(node, dict):
        return ''
    text = node.get('text', '')
    for child in node.get('children', []):
        text += _extract_text(child)
    return text.strip()


def analyze_board(board: List[List[int]]) -> Dict[str, Any]:
    n = len(board)
    if n == 0:
        return {}

    # 坐标转 A1 格式
    def coord_to_str(r: int, c: int) -> str:
        return f"{chr(ord('A') + c)}{r + 1}"

    def convert_coords(obj):
        if isinstance(obj, list) or isinstance(obj, tuple):
            if len(obj) == 2 and all(isinstance(x, int) for x in obj):
                return coord_to_str(obj[0], obj[1])
            return [convert_coords(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: convert_coords(v) for k, v in obj.items()}
        return obj

    # 获取所有五格线
    def get_all_lines() -> List[List[Tuple[int, int]]]:
        lines = []
        for r in range(n):
            lines.append([(r, c) for c in range(n)])
        for c in range(n):
            lines.append([(r, c) for r in range(n)])
        for diff in range(-n + 1, n):
            line = [(r, r - diff) for r in range(n) if 0 <= r - diff < n]
            if len(line) >= 5:
                lines.append(line)
        for sm in range(0, 2 * n - 1):
            line = [(r, sm - r) for r in range(n) if 0 <= sm - r < n]
            if len(line) >= 5:
                lines.append(line)
        return lines

    lines = get_all_lines()

    result = {
        "board": {"black": [], "white": []},
        "features": {
            "black": {"live_two": [], "live_three": [], "sleeping_three": [], "dead_four": [], "threat_points": []},
            "white": {"live_two": [], "live_three": [], "sleeping_three": [], "dead_four": [], "threat_points": []}
        }
    }

    # 收集原始坐标（待转换）
    for r in range(n):
        for c in range(n):
            if board[r][c] == 1:
                result["board"]["black"].append((r, c))
            elif board[r][c] == 2:
                result["board"]["white"].append((r, c))

    # 滑窗扫描
    for color in [1, 2]:
        color_key = "black" if color == 1 else "white"
        live_two_set, live_three_set, sleeping_three_set, dead_four_set, threat_set = set(), set(), set(), set(), set()

        for line in lines:
            line_len = len(line)
            for start in range(line_len - 4):
                window = line[start:start + 5]
                vals = [board[r][c] for (r, c) in window]
                cnt0 = vals.count(0)
                cnt_color = vals.count(color)

                left_open = (start > 0 and board[line[start - 1][0]][line[start - 1][1]] == 0)
                right_open = (start + 5 < line_len and board[line[start + 5][0]][line[start + 5][1]] == 0)
                both_open = left_open and right_open

                # 仅提取该颜色棋子的坐标
                color_coords = [window[i] for i in range(5) if vals[i] == color]

                if cnt_color == 3 and cnt0 == 2:
                    coords = tuple(sorted(color_coords))   # 长度为3
                    if both_open:
                        live_three_set.add(coords)
                    else:
                        sleeping_three_set.add(coords)
                elif cnt_color == 4 and cnt0 == 1:
                    empty_idx = vals.index(0)
                    threat_pos = window[empty_idx]
                    threat_set.add(threat_pos)   # 单个坐标
                    if not left_open and not right_open:
                        dead_four_set.add(tuple(sorted(color_coords)))   # 长度为4
                elif cnt_color == 2 and cnt0 == 3:
                    if both_open:
                        live_two_set.add(tuple(sorted(color_coords)))   # 长度为2

        # 存入（此时还是 (r,c) 元组）
        result["features"][color_key]["live_two"] = [list(coords) for coords in live_two_set]
        result["features"][color_key]["live_three"] = [list(coords) for coords in live_three_set]
        result["features"][color_key]["sleeping_three"] = [list(coords) for coords in sleeping_three_set]
        result["features"][color_key]["dead_four"] = [list(coords) for coords in dead_four_set]
        result["features"][color_key]["threat_points"] = list(threat_set)   # 已是单个坐标列表

    # 统一转换为字符串
    return convert_coords(result)


def _parse_board_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    从快照 JSON 中解析棋盘数据。
    返回格式同 get_board_data 的 data 部分。
    """
    tree = snapshot.get('tree')
    if not tree:
        return {"error": "快照缺少 tree 字段"}

    # 1. 找到 SVG 节点
    svg_node = _find_node(tree, tag='svg', attrs={'id': 'svg'})
    if not svg_node:
        return {"error": "未找到 SVG 节点"}

    # 获取 SVG 的屏幕坐标和尺寸
    svg_rect = svg_node.get('_rect')
    if not svg_rect:
        return {"error": "SVG 缺少 _rect 信息"}
    sx, sy, sw, sh = svg_rect['x'], svg_rect['y'], svg_rect['width'], svg_rect['height']
    viewBox_left, viewBox_top, viewBox_width, viewBox_height = -80, -80, 160, 160

    def screen_to_view(px, py):
        vx = viewBox_left + (px - sx) / sw * viewBox_width
        vy = viewBox_top + (py - sy) / sh * viewBox_height
        return vx, vy

    # 2. 收集所有 text 节点（数字和字母）
    all_texts = _find_all_nodes(tree, tag='text')
    row_positions = {}  # row_index -> viewBox y
    col_positions = {}  # col_index -> viewBox x

    for text_node in all_texts:
        txt = _extract_text(text_node).strip()
        rect = text_node.get('_rect')
        if not rect:
            continue
        px = rect['x'] + rect['width'] / 2
        py = rect['y'] + rect['height'] / 2
        vx, vy = screen_to_view(px, py)

        if re.match(r'^[1-9]|1[0-5]$', txt):
            row = int(txt) - 1
            row_positions[row] = vy
        elif re.match(r'^[A-O]$', txt):
            col = ord(txt) - ord('A')
            col_positions[col] = vx

    # 补齐缺失的行/列（假设等距）
    if len(row_positions) < BOARD_SIZE:
        sorted_rows = sorted(row_positions.items())
        if sorted_rows:
            first_row, first_y = sorted_rows[0]
            last_row, last_y = sorted_rows[-1]
            step = (last_y - first_y) / (last_row - first_row) if last_row != first_row else 1
            for i in range(BOARD_SIZE):
                if i not in row_positions:
                    row_positions[i] = first_y + step * (i - first_row)
    if len(col_positions) < BOARD_SIZE:
        sorted_cols = sorted(col_positions.items())
        if sorted_cols:
            first_col, first_x = sorted_cols[0]
            last_col, last_x = sorted_cols[-1]
            step = (last_x - first_x) / (last_col - first_col) if last_col != first_col else 1
            for i in range(BOARD_SIZE):
                if i not in col_positions:
                    col_positions[i] = first_x + step * (i - first_col)

    # 3. 读取棋子
    all_uses = _find_all_nodes(tree, tag='use', attrs={'xlink:href': '#piece'})
    board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]

    for use in all_uses:
        x_str = use.get('x')
        y_str = use.get('y')
        if x_str is None or y_str is None:
            continue
        try:
            vx = float(x_str)
            vy = float(y_str)
        except ValueError:
            continue
        fill = use.get('fill', '')
        color = 0
        if 'black' in fill:
            color = 1
        elif 'white' in fill:
            color = 2
        else:
            continue

        min_dist = float('inf')
        best_row, best_col = -1, -1
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cx = col_positions.get(c)
                cy = row_positions.get(r)
                if cx is None or cy is None:
                    continue
                dist = (vx - cx) ** 2 + (vy - cy) ** 2
                if dist < min_dist:
                    min_dist = dist
                    best_row, best_col = r, c
        if best_row >= 0 and best_col >= 0 and min_dist < 20:
            board[best_row][best_col] = color

    # 5. 识别“我”的座位和颜色
    my_seat = -1
    my_color = 0

    # 在所有节点中查找包含文本“我”的节点
    all_nodes = _find_all_nodes(tree)  # 递归所有节点
    for node in all_nodes:
        if isinstance(node, dict):
            text = node.get('text', '').strip()
            if text == '我':
                # 向上找父级 id 为 userseat0 或 userseat1
                # 由于我们的树是嵌套的，但 _find_node 无法向上回溯，需要从树中搜索包含这个节点的路径。
                # 简单方法：直接查找 userseat0 和 userseat1 下是否有包含“我”的子节点
                break

    # 更高效：直接检查两个座位节点
    seat0 = _find_node(tree, tag='div', attrs={'id': 'userseat0'})
    seat1 = _find_node(tree, tag='div', attrs={'id': 'userseat1'})

    def has_me(node):
        if not isinstance(node, dict):
            return False
        if node.get('text', '').strip() == '我':
            return True
        for child in node.get('children', []):
            if has_me(child):
                return True
        return False

    if seat0 and has_me(seat0):
        my_seat = 0
        my_color = 1  # 通常 seat0 执黑
    elif seat1 and has_me(seat1):
        my_seat = 1
        my_color = 2  # 通常 seat1 执白
    else:
        # 未找到“我”，可能未登录或页面不同，留空
        pass

    # 4. 状态信息
    turn = 1
    game_over = False
    winner = None
    message = ''

    # 收集所有文本节点，寻找状态描述
    all_text_nodes = _find_all_nodes(tree)  # 所有节点，遍历检查文本
    status_texts = []
    for node in all_text_nodes:
        if isinstance(node, dict):
            text = node.get('text', '').strip()
            if text and any(keyword in text for keyword in ['等你下棋', '黑棋', '白棋', '胜', '赢', '认输']):
                status_texts.append(text)

    for st in status_texts:
        if '等你下棋' in st:
            message = st
            turn = 1
            break
        elif '黑棋' in st:
            message = st
            turn = 1
            if '胜' in st or '赢' in st:
                game_over = True
                winner = 1
            break
        elif '白棋' in st:
            message = st
            turn = 2
            if '胜' in st or '赢' in st:
                game_over = True
                winner = 2
            break
    else:
        if status_texts:
            message = status_texts[0]

    if '认输' in message:
        game_over = True

    # 玩家名
    players = {'black': '玩家1', 'white': '玩家2'}
    seat0 = _find_node(tree, tag='div', attrs={'id': 'userseat0'})
    if seat0:
        name_node = _find_node(seat0, tag='div', attrs={'class': 'text-2xl overflow-hidden'})  # 修正
        if name_node:
            players['black'] = _extract_text(name_node)
    seat1 = _find_node(tree, tag='div', attrs={'id': 'userseat1'})
    if seat1:
        name_node = _find_node(seat1, tag='div', attrs={'class': 'text-2xl overflow-hidden'})  # 修正
        if name_node:
            players['white'] = _extract_text(name_node)

    return {
        'board': board,
        'turn': "黑棋" if turn == 1 else "白棋",  # 现在返回 "黑棋" 或 "白棋"
        'game_over': game_over,
        'winner': winner,
        'message': message,
        'players': players,
        'my_seat': my_seat,
        'my_color': "黑棋" if my_color == 1 else ("白棋" if my_color == 2 else "未知"),
    }


def get_board_data():
    if not _check_game():
        return {"success": False, "data": f"你未打开{URL}五子棋网页，不可使用当前工具"}

    snapshot_str = tool_browser_get_json_snapshot(max_depth=50, max_children=600, max_nodes=600)
    try:
        snapshot = json.loads(snapshot_str)
    except json.JSONDecodeError as e:
        return {"success": False, "data": f"快照解析失败: {e}"}

    result = _parse_board_from_snapshot(snapshot)
    result["board"] = analyze_board(result["board"])
    if 'error' in result:
        return {"success": False, "data": result['error']}
    return {"success": True, "data": result}


def drop_stone(pos: str):
    if not _check_game():
        return {"success": False, "data": f"你未打开{URL}五子棋网页，不可使用当前工具"}

    # 检查是否为己方回合
    board_status = get_board_data()
    if not board_status["success"]:
        return {"success": False, "data": f"无法获取棋盘状态: {board_status['data']}"}

    state = board_status["data"]
    if state["game_over"]:
        return {"success": False, "data": "游戏已结束，不能落子"}

    if "等你下棋" not in state["message"]:
        return {"success": False, "data": f"当前不是你的回合（状态: {state['message']}），请等待"}

    coord = _parse_pos(pos)
    if coord is None:
        return {"success": False, "data": f"无效的坐标格式: {pos}，请使用如 'A1' 或 '1,1'"}

    row, col = coord

    js_click = f"""
    (function() {{
        const BOARD_SIZE = 15;
        const svg = document.getElementById('svg');
        if (!svg) return JSON.stringify({{ error: 'SVG not found' }});

        const textEls = svg.querySelectorAll('text');
        const rowPositions = new Map();
        const colPositions = new Map();
        textEls.forEach(el => {{
            const txt = el.textContent.trim();
            if (/^[1-9]|1[0-5]$/.test(txt)) {{
                const row = parseInt(txt, 10) - 1;
                const rect = el.getBoundingClientRect();
                rowPositions.set(row, rect.top + rect.height / 2);
            }} else if (/^[A-O]$/.test(txt)) {{
                const col = txt.charCodeAt(0) - 65;
                const rect = el.getBoundingClientRect();
                colPositions.set(col, rect.left + rect.width / 2);
            }}
        }});

        function interpolate(map, size) {{
            const keys = Array.from(map.keys()).sort((a,b) => a-b);
            const newMap = new Map();
            if (keys.length < 2) return newMap;
            const firstKey = keys[0];
            const lastKey = keys[keys.length - 1];
            const firstVal = map.get(firstKey);
            const lastVal = map.get(lastKey);
            const step = (lastVal - firstVal) / (lastKey - firstKey);
            for (let i = 0; i < size; i++) {{
                if (map.has(i)) newMap.set(i, map.get(i));
                else newMap.set(i, firstVal + step * (i - firstKey));
            }}
            return newMap;
        }}

        const rowMap = interpolate(rowPositions, BOARD_SIZE);
        const colMap = interpolate(colPositions, BOARD_SIZE);
        if (rowMap.size !== BOARD_SIZE || colMap.size !== BOARD_SIZE) {{
            return JSON.stringify({{ error: '坐标映射不完整' }});
        }}

        const targetRow = {row};
        const targetCol = {col};
        const cx = colMap.get(targetCol);
        const cy = rowMap.get(targetRow);
        if (cx === undefined || cy === undefined) {{
            return JSON.stringify({{ error: '坐标超出范围' }});
        }}

        const element = document.elementFromPoint(cx, cy);
        if (!element) {{
            return JSON.stringify({{ error: '未找到点击目标' }});
        }}

        const evt = new MouseEvent('click', {{
            clientX: cx,
            clientY: cy,
            bubbles: true,
            cancelable: true,
        }});
        element.dispatchEvent(evt);

        return JSON.stringify({{ success: true, message: '落子成功' }});
    }})()
    """

    result_str = tool_browser_execute_js(js_click, timeout=10)
    try:
        data = json.loads(result_str)
        if data.get("error"):
            return {"success": False, "data": data["error"]}
        return {"success": True, "data": data.get("message", "落子指令已执行")}
    except json.JSONDecodeError:
        return {"success": False, "data": f"落子响应解析失败: {result_str}"}


TOOLS["huliqin_wzq_get_board"] = {
    "description": "获取五子棋游戏（hullqin.cn/wzq/*）当前棋盘状态、回合信息、胜负情况以及详细的棋型特征分析。返回内容包括棋盘坐标（A1~O15 "
                   "格式）、当前轮到谁、游戏是否结束、胜者、双方玩家名称，以及提取的活二、活三、眠三、冲四、威胁点等特征。",
    "parameters": {},
    "execute": get_board_data,
}

TOOLS["huliqin_wzq_drop_stone"] = {
    "description": "在五子棋(https://game.hullqin.cn/wzq/*)棋盘上落子。仅当页面显示“等你下棋”时可用（即轮到己方回合）。坐标支持 'A1'~'O15' 或 '1,1'~'15,"
                   "15' 格式。内部通过模拟点击棋盘上对应位置的 DOM 元素来实现落子。",
    "parameters": {
        "pos": {
            "type": "string",
            "required": True,
            "description": "落子坐标，例如 'H8' 或 '8,8'（行列从1开始）"
        }
    },
    "execute": drop_stone,
}


if __name__ == '__main__':
    from ds.agentTools.broswer.browser import *


    def test():
        tool_browser_navigate("https://game.hullqin.cn/wzq/n406")
        data = get_board_data()["data"]
        print(data)

    test()
