#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/08/22 22:26
# @Author  : Wu_RH
# @FileName: wzq.py

from typing import Dict, Any, Optional, Tuple, List

import json
import re

from ds.agentTools import TOOLS
from ds.agentTools.broswer.browser import (
    tool_browser_get_page_info,
    tool_browser_get_json_snapshot,
    tool_browser_execute_js,
)
from ds.agentTools.broswer.gameHullqin.wzq_analyze import analyze_board

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
                row = int(parts[0])
                col = int(parts[1])
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


def _parse_board_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    从快照 JSON 中解析棋盘数据。
    返回格式同 get_board_data 的 data 部分。
    """
    import re
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

    # 4. 状态信息（精确匹配状态文本）
    message = ""

    # 递归查找 class 包含 'space-x-4' 的 div
    status_container: Optional[Dict] = None

    def find_space_x_4(node):
        nonlocal status_container
        if not isinstance(node, dict):
            return
        if node.get('tag') == 'div':
            cls = node.get('class', '')
            if cls and 'space-x-4' in cls:
                status_container = node
                return
        for child in node.get('children', []):
            find_space_x_4(child)
            if status_container:
                return

    find_space_x_4(tree)
    if not status_container:
        return {"error": "未找到状态容器 (space-x-4)"}

    # 取第一个 span 子节点的文本（去除 emoji 和空格，但保留关键文字）
    span_node = _find_node(status_container, tag='span')
    if span_node:
        raw_text = _extract_text(span_node)
        # 去除 emoji 和前后空格，只保留中文部分
        import re
        clean_text = re.sub(r'[^\u4e00-\u9fa5]', '', raw_text)  # 仅保留汉字
        if clean_text:
            message = clean_text
        else:
            message = raw_text.strip()
    else:
        # 若没有 span，取第一个非 button 的文本节点
        for child in status_container.get('children', []):
            if child.get('tag') == 'button':
                continue
            txt = _extract_text(child)
            if txt:
                raw_text = txt
                clean_text = re.sub(r'[^\u4e00-\u9fa5]', '', raw_text)
                message = clean_text if clean_text else raw_text.strip()
                break

    if not message:
        return {"error": "状态容器中未找到有效状态文本"}

    # 确定我方和对方颜色
    my_color_str = "黑棋" if my_color == 1 else ("白棋" if my_color == 2 else None)
    opponent_color_str = "白棋" if my_color == 1 else ("黑棋" if my_color == 2 else None)

    # 精确匹配状态
    if message == "恭喜获胜":
        game_over = True
        winner = my_color_str
        turn = my_color_str  # 赢了，回合无所谓
    elif message == "对方胜利":
        game_over = True
        winner = opponent_color_str
        turn = opponent_color_str
    elif message == "等你下棋":
        game_over = False
        turn = my_color_str
        winner = None
    elif message == "等对方下棋":
        game_over = False
        turn = opponent_color_str
        winner = None
    elif message == "你请求悔棋中":
        # 己方请求悔棋，对方需响应，此时视为对方回合
        game_over = False
        turn = opponent_color_str
        winner = None
    else:
        # 未知状态，尝试从规则信息（如“无禁手”）推断，但此时没有明确状态，假设游戏未结束
        # 但为了安全，报错
        return {"error": f"未知的状态消息: {message}"}

    # 如果 game_over 但 winner 为 None，报错
    if game_over and winner is None:
        return {"error": f"游戏结束但无法确定赢家: {message}"}

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
        'turn': turn,  # 现在返回 "黑棋" 或 "白棋"
        'game_over': game_over,
        'winner': winner,
        'message': message,
        'players': players,
        'my_seat': my_seat,
        'my_color': my_color,
    }


def _parse_room_info_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    从快照中提取房间基础信息（不依赖棋盘元素）。
    返回：room_id, players, my_seat, my_color, game_started, message
    """
    tree = snapshot.get('tree')
    if not tree:
        return {"error": "快照缺少 tree 字段"}

    # 房间号（文本 "房间号: xxx"）
    room_id = "未知"
    all_texts = _find_all_nodes(tree)
    for node in all_texts:
        if isinstance(node, dict):
            text = node.get('text', '').strip()
            if text.startswith('房间号:'):
                room_id = text.split('房间号:')[1].strip()
                break

    # 玩家名（座位可能为空）
    players = {'black': '空位', 'white': '空位'}
    seat0 = _find_node(tree, tag='div', attrs={'id': 'userseat0'})
    if seat0:
        name_node = _find_node(seat0, tag='div', attrs={'class': 'text-2xl overflow-hidden'})
        if name_node:
            players['black'] = _extract_text(name_node)
    seat1 = _find_node(tree, tag='div', attrs={'id': 'userseat1'})
    if seat1:
        name_node = _find_node(seat1, tag='div', attrs={'class': 'text-2xl overflow-hidden'})
        if name_node:
            players['white'] = _extract_text(name_node)

    # 识别“我”的座位
    my_seat = -1
    my_color = 0

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
        my_color = 1
    elif seat1 and has_me(seat1):
        my_seat = 1
        my_color = 2

    # 直接检查 SVG 棋盘是否存在
    svg_node = _find_node(tree, tag='svg', attrs={'id': 'svg'})
    game_started = svg_node is not None

    # 状态消息（如“房主执黑先手”）
    message = ''
    for node in all_texts:
        if isinstance(node, dict):
            text = node.get('text', '').strip()
            if any(k in text for k in ('房主执黑', '无禁手', '有禁手', '开始游戏')):
                message = text
                break

    return {
        'room_id': room_id,
        'players': players,
        'my_seat': my_seat,
        'my_color': "黑棋" if my_color == 1 else ("白棋" if my_color == 2 else "未知"),
        'game_started': game_started,
        'message': message,
    }


def get_board_data() -> Dict[str, Any]:
    if not _check_game():
        return {"success": False, "data": f"你未打开{URL}五子棋网页，不可使用当前工具"}

    snapshot_str = tool_browser_get_json_snapshot(max_depth=50, max_children=600, max_nodes=600)
    try:
        snapshot = json.loads(snapshot_str)
    except json.JSONDecodeError as e:
        return {"success": False, "data": f"快照解析失败: {e}"}

    # 先获取房间状态，如果游戏未开始则直接返回
    room_info = _parse_room_info_from_snapshot(snapshot)
    if room_info.get('error'):
        return {"success": False, "data": room_info['error']}
    if not room_info['game_started']:
        return {"success": False, "data": "游戏尚未开始，无法获取棋盘数据"}

    # 游戏已开始，解析棋盘
    result = _parse_board_from_snapshot(snapshot)
    if 'error' in result:
        return {"success": False, "data": result['error']}
    # 分析特征
    result['board'] = analyze_board(result['board'])
    # 附加房间信息（方便调用者）
    result['room_id'] = room_info['room_id']
    result['game_started'] = True
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
    if f"({row},{col})" in ';'.join(
        board_status["data"]["board"]["board"]["black"] +
        board_status["data"]["board"]["board"]["white"]
    ):
        return {"success": False, "data": f"该位置已经落子了"}

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
        return {
            "success": True,
            "data": {
                "msg": data.get("message", "落子指令已执行"),
                "data": get_board_data()
            }
        }
    except json.JSONDecodeError:
        return {"success": False, "data": f"落子响应解析失败: {result_str}"}


def huliqin_wzq_get_room_status() -> Dict[str, Any]:
    """获取房间状态，即使游戏未开始也能获取基本信息。若游戏已开始，额外合并棋盘状态。"""
    if not _check_game():
        return {"success": False, "data": f"你未打开{URL}五子棋网页，不可使用当前工具"}

    snapshot_str = tool_browser_get_json_snapshot(max_depth=50, max_children=600, max_nodes=600)
    try:
        snapshot = json.loads(snapshot_str)
    except json.JSONDecodeError as e:
        return {"success": False, "data": f"快照解析失败: {e}"}

    room_info = _parse_room_info_from_snapshot(snapshot)
    if room_info.get('error'):
        return {"success": False, "data": room_info['error']}

    # 如果游戏已开始，获取完整棋盘状态并合并
    if room_info['game_started']:
        board_result = get_board_data()
        if board_result['success']:
            board_data: dict = board_result['data']
            # 合并，保留房间基础信息，覆盖回合/胜负/消息等
            room_info.update({
                'turn': board_data.get('turn'),
                'game_over': board_data.get('game_over'),
                'winner': board_data.get('winner'),
                'message': board_data.get('message', room_info['message']),
                'board': board_data.get('board'),
                'features': board_data.get('features'),
            })
        # 若获取棋盘失败，仅返回房间信息（部分字段可能缺失）

    return {"success": True, "data": room_info}


def huliqin_wzq_join_seat(seat: int = 0):
    if not _check_game():
        return {"success": False, "data": f"你未打开{URL}五子棋网页，不可使用当前工具"}

    # 获取房间信息（不依赖棋盘）
    status = huliqin_wzq_get_room_status()
    if not status["success"]:
        return status
    state = status["data"]

    # 检查座位是否被占用（非“空位”）
    if seat == 0:
        if state["players"]["black"] not in ("空位", "未知"):
            return {"success": True, "data": f"座位 {seat} 已被占用（{state['players']['black']}），无需加入"}
    else:
        if state["players"]["white"] not in ("空位", "未知"):
            return {"success": True, "data": f"座位 {seat} 已被占用（{state['players']['white']}），无需加入"}

    # 点击座位按钮（ref 固定为 E4/E5）
    ref_map = {0: "E4", 1: "E5"}
    ref = ref_map.get(seat)
    if not ref:
        return {"success": False, "data": f"无效的座位号: {seat}"}

    js_click_ref = f"""
    (function() {{
        const el = document.querySelector('[data-ds-ref="{ref}"]');
        if (!el) return JSON.stringify({{ error: '未找到座位按钮' }});
        el.click();
        return JSON.stringify({{ success: true, message: '已点击座位 {seat}' }});
    }})()
    """
    result_str = tool_browser_execute_js(js_click_ref, timeout=5)
    try:
        data = json.loads(result_str)
        if data.get("error"):
            return {"success": False, "data": data["error"]}
        return {"success": True, "data": data.get("message", f"已尝试加入座位 {seat}")}
    except json.JSONDecodeError:
        return {"success": False, "data": f"执行加入座位失败: {result_str}"}


def huliqin_wzq_wait_my_turn(timeout: int = 30, poll_interval: float = 1.0):
    """
    阻塞等待直到页面显示“等你下棋”（即轮到己方回合），超时则返回失败。

    :param timeout: 最大等待时间（秒）
    :param poll_interval: 轮询间隔（秒）
    :return: {"success": bool, "data": str}
    """
    import time
    start = time.time()
    while time.time() - start < timeout:
        status = get_board_data()
        if not status["success"]:
            # 如果获取状态失败，可能是游戏未开始或页面变化，继续等待（但记录错误）
            # 这里我们直接返回错误，或可以选择继续轮询。
            # 为了鲁棒性，如果返回的是“游戏尚未开始”，我们继续等待，因为可能正在开始中。
            if "游戏尚未开始" in status.get("data", ""):
                time.sleep(poll_interval)
                continue
            return status
        if "等你下棋" in status["data"].get("message", ""):
            return {
                "success": True,
                "data": {
                    "msg": f"已轮到你的回合（等待 {time.time() - start:.1f}s）",
                    "data": get_board_data(),
                }
            }
        time.sleep(poll_interval)
    return {"success": False, "data": f"等待超时（{timeout}s），仍未轮到你的回合"}


TOOLS["huliqin_wzq_get_board"] = {
    "description": "获取五子棋游戏（hullqin.cn/wzq/*）当前棋盘状态、回合信息、胜负情况以及详细的棋型特征分析。返回内容包括棋盘坐标（A1~O15 "
                   "格式）、当前轮到谁、游戏是否结束、胜者、双方玩家名称，以及提取的活二、活三、眠三、冲四、威胁点等特征。",
    "parameters": {},
    "execute": get_board_data,
}

TOOLS["huliqin_wzq_drop_stone"] = {
    "description": "在五子棋(https://game.hullqin.cn/wzq/*)棋盘上落子。仅当页面显示“等你下棋”时可用（即轮到己方回合）。坐标支持 'A1'~'O15' 或 '1,1'~'15,"
                   "15' 格式。内部通过模拟点击棋盘上对应位置的 DOM 元素来实现落子。且在工具结束后自动返回board_data",
    "parameters": {
        "pos": {
            "type": "string",
            "required": True,
            "description": "落子坐标，例如 'H8' 或 '8,8'（行列从1开始）"
        }
    },
    "execute": drop_stone,
}

TOOLS["huliqin_wzq_join_seat"] = {
    "description": "加入指定的座位（0 或 1）。如果座位已被占用则直接返回成功，否则点击座位按钮加入游戏。",
    "parameters": {
        "seat": {"type": "integer", "required": False, "default": 0, "description": "座位号，0 或 1"}
    },
    "execute": huliqin_wzq_join_seat,
}

TOOLS["huliqin_wzq_get_room_status"] = {
    "description": "获取当前房间的详细信息，包括房间号、玩家、我的座位/颜色、当前回合、是否结束等。即使游戏未开始也能获取基本信息。",
    "parameters": {},
    "execute": huliqin_wzq_get_room_status,
}

TOOLS["huliqin_wzq_wait_my_turn"] = {
    "description": "阻塞等待直到页面显示“等你下棋”（即轮到己方回合）。可设置超时时间（秒）。且自动返回board_data",
    "parameters": {
        "timeout": {"type": "integer", "required": False, "default": 30, "description": "最大等待时间（秒）"},
        "poll_interval": {"type": "number", "required": False, "default": 1.0, "description": "轮询间隔（秒）"}
    },
    "execute": huliqin_wzq_wait_my_turn,
}


if __name__ == '__main__':
    from ds.agentTools.broswer.browser import tool_browser_navigate
    from ds.config import CONFIG


    def test():
        CONFIG["SESSION_DIR"] = r"D:\0.0\lib\my_python\dsBrowser\session\session2"
        tool_browser_navigate("https://game.hullqin.cn/wzq/14mv")
        data = get_board_data()
        print(data)
        data = drop_stone("B2")
        print(data)
        data = huliqin_wzq_get_room_status()
        print(data)

    test()
