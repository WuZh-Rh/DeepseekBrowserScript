#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/08/23 02:47
# @Author  : Wu_RH
# @FileName: wzq_analyze.py
from typing import List, Tuple, Dict, Any, Optional

WINDOW_SIZE = 6


# ---------- 坐标转换辅助 ----------
def _coord_to_str(r: int, c: int) -> str:
    return f"{chr(ord('A') + c)}{r + 1}({r},{c})"


def _convert_coords(obj):
    """递归将字典/列表中的 [r,c] 转换为 A1 字符串"""
    if isinstance(obj, list) or isinstance(obj, tuple):
        if len(obj) == 2 and all(isinstance(x, int) for x in obj):
            return _coord_to_str(obj[0], obj[1])
        return [_convert_coords(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _convert_coords(v) for k, v in obj.items()}
    return obj


def _convert_window(window: List[int], my_color: int) -> List[int]:
    """
    将原始窗口值（0/1/2/-1）转换为当前视角的（0=空, 1=己方, 2=对方）
    -1 视为对方棋子
    """
    converted = []
    for val in window:
        if val == 0:
            converted.append(0)  # 边界外视为对方
        elif val == my_color:
            converted.append(1)
        elif val != my_color:
            converted.append(2)
    return converted


def _get_cell_value(board: List[List[int]], r: int, c: int) -> int:
    """获取棋盘上 (r,c) 的值，越界返回 -1（视为对方）"""
    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0
    if 0 <= r < rows and 0 <= c < cols:
        return board[r][c]
    return -1


def _record_feature(
    window: List[int], result: Dict,
    color: int, feature_type: str,
    positions: List[Optional[Tuple[int, int]]]
):
    """
    记录特征到 result 中
    color: 1 或 2
    feature_type: 'live_two', 'live_three', 'sleeping_three', 'dead_four', 'live_four', 'win'
    注意：只记录有效坐标（过滤 None）
    """
    # 根据颜色选择对应键
    color_key = "black" if color == 1 else "white"
    # 过滤掉 None
    valid_pos = [p for v, p in zip(window, positions) if p is not None and v == 1]
    if not valid_pos:
        return
    # 添加到相应列表（这里我们暂时用 append，后续可做去重）
    if valid_pos in result["features"][color_key][feature_type]:
        return
    result["features"][color_key][feature_type].append(valid_pos)


def _process_window(
    window: List[int],
    color: int,
    positions: List[Optional[Tuple[int, int]]],
    result: Dict,
    board: List[List[int]]
):
    """
    窗口判断函数
    window: 长度为6，元素 0/1/2（已转换视角）
    color: 当前视角颜色 (1 或 2)
    positions: 每个格子对应的原始棋盘坐标 (row, col) 或 None（边界外）
    result: 结果容器
    board: 原始棋盘（用于检查外侧）
    """
    # 快速过滤：如果对方棋子超过1个，或者对方在中间4个位置，直接返回
    if window.count(2) > 1:
        return
    if any(window[i] == 2 for i in range(1, 5)):
        return

    self_count = window.count(1)
    if self_count < 2:
        return

    # ---------- 计算第七位置（如果有对方在边缘） ----------
    seventh_pos = None  # 初始化变量为 None（元组或 None）
    if window[0] == 2:
        # 对方在左边缘（位置0），第七位置是位置0的左侧再左一格
        base = positions[0]          # 位置0的棋盘坐标
        if base is not None and positions[1] is not None:
            # 方向向量 = positions[1] - positions[0]
            dr = positions[1][0] - positions[0][0]
            dc = positions[1][1] - positions[0][1]
            seventh_pos = (base[0] - dr, base[1] - dc)   # 向左扩一格
        else:
            seventh_pos = None      # 已在边界外，第七位置也在边界外
    elif window[5] == 2:
        # 对方在右边缘（位置5），第七位置是位置5的右侧再右一格
        base = positions[5]
        if base is not None and positions[4] is not None:
            dr = positions[4][0] - positions[5][0]
            dc = positions[4][1] - positions[5][1]
            seventh_pos = (base[0] - dr, base[1] - dc)   # 向右扩一格
        else:
            seventh_pos = None
    # 如果窗口没有对方棋子，seventh_pos 保持 None

    # 后续判断分支中，可以通过 _get_cell_value(board, *seventh_pos) 获取第七位置的值
    # 若 seventh_pos 为 None，直接视为对方棋子（值为 2）
    seventh_val = 2 if seventh_pos is None else _get_cell_value(board, seventh_pos[0], seventh_pos[1])

    # ---------- 分支1：没有对方棋子 ----------
    if 2 not in window:
        if self_count == 2:
            if window[0] == 1 or window[5] == 1:
                return
            _record_feature(window, result, color, "live_two", positions)

        elif self_count == 3:
            span = 5 - window[::-1].index(1) - window.index(1)
            if span <= 3:
                if window[0] == 1 or window[5] == 1:
                    return
                _record_feature(window, result, color, "live_three", positions)
            elif span == 4:
                _record_feature(window, result, color, "sleeping_three", positions)
            else:  # span == 5
                return

        elif self_count == 4:
            span = 5 - window[::-1].index(1) - window.index(1)
            if span == 5:
                return
            elif span == 4:
                _record_feature(window, result, color, "dead_four", positions)
            elif span == 3:
                if window[0] == 1 or window[5] == 1:
                    return
                else:
                    _record_feature(window, result, color, "live_four", positions)
            else:
                return

        elif self_count == 5:
            if window[0] == 0 or window[5] == 0:
                _record_feature(window, result, color, "win", positions)
            else:
                return

        else:  # self_count == 6
            _record_feature(window, result, color, "win", positions)

    # ---------- 分支2：边缘有一个对方棋子 ----------
    else:
        opp_left = (window[0] == 2)

        if self_count == 2:
            if window[1] == 1 if opp_left else window[4] == 1:
                _record_feature(window, result, color, "sleeping_two", positions)
            else:
                if seventh_val == 2:
                    _record_feature(window, result, color, "sleeping_two", positions)
                else:
                    _record_feature(window, result, color, "live_two", positions)

        elif self_count == 3:
            span = 5 - window[::-1].index(1) - window.index(1)
            if span <= 3:
                if window[1] == 1 if opp_left else window[4] == 1:
                    _record_feature(window, result, color, "sleeping_three", positions)
                else:
                    if window[5] == 1 if opp_left else window[0] == 1:
                        return
                    if seventh_val == 2:
                        _record_feature(window, result, color, "sleeping_three", positions)  # 冲三
                    else:
                        _record_feature(window, result, color, "live_three", positions)      # 按你的定义算活三
            elif span == 4:
                _record_feature(window, result, color, "sleeping_three", positions)
            else:  # span == 5
                return

        elif self_count == 4:
            span = 5 - window[::-1].index(1) - window.index(1)
            if span == 4:
                _record_feature(window, result, color, "dead_four", positions)
            elif span == 3:
                if window[1] == 1 if opp_left else window[4] == 1:
                    _record_feature(window, result, color, "dead_four", positions)
                else:
                    if window[5] == 1 if opp_left else window[0] == 1:
                        return
                    # 其他情况按你的规则没有，但若出现，我们保守返回
            else:
                return

        elif self_count == 5:
            _record_feature(window, result, color, "win", positions)

        else:  # self_count == 6
            _record_feature(window, result, color, "win", positions)


def analyze_board(board: List[List[int]]) -> Dict[str, Any]:
    """
    输入：二维数组 board，0=空，1=黑，2=白
    输出：结果容器（特征列表暂为空）
    """

    result = {
        "board": {"black": [], "white": []},
        "features": {
            "black": {
                "live_two": [],
                "sleeping_two": [],
                "live_three": [],
                "sleeping_three": [],
                "dead_four": [],
                "live_four": [],
                "threat_points": []
            },
            "white": {
                "live_two": [],
                "sleeping_two": [],
                "live_three": [],
                "sleeping_three": [],
                "live_four": [],
                "dead_four": [],
                "threat_points": []
            }
        }
    }

    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0

    for row in range(rows):
        for col in range(cols):
            if board[row][col] == 1:
                result["board"]["black"].append([row, col])
            elif board[row][col] == 2:
                result["board"]["white"].append([row, col])

    # 扩展棋盘，四周扩一圈，填充 -1（表示边界外，视为任何一方的对方）
    padded = [[-1] * (cols + 2) for _ in range(rows + 2)]
    for r in range(rows):
        for c in range(cols):
            padded[r + 1][c + 1] = board[r][c]

    directions = [
        (0, 1),  # 水平
        (1, 0),  # 垂直
        (1, 1),  # 主对角线
        (1, -1)  # 副对角线
    ]

    # 遍历所有方向及所有可能的起始点
    for dr, dc in directions:
        max_r = rows + 1
        max_c = cols + 1

        if dr != 0:
            max_start_r = max_r - 5
        else:
            max_start_r = max_r - 1
        if dc != 0:
            max_start_c = max_c - 5
        else:
            max_start_c = max_c - 1

        for sr in range(max_start_r + 1):
            for sc in range(max_start_c + 1):
                window_cells = []
                positions = []
                for step in range(WINDOW_SIZE):
                    r = sr + step * dr
                    c = sc + step * dc
                    val = padded[r][c]
                    orig_r = r - 1
                    orig_c = c - 1
                    if 0 <= orig_r < rows and 0 <= orig_c < cols:
                        positions.append((orig_r, orig_c))
                    else:
                        positions.append(None)
                    window_cells.append(val)

                # 分别从黑方和白方视角处理
                for color in [1, 2]:
                    win = _convert_window(window_cells, color)
                    _process_window(win, color, positions, result, board)

    # 将所有坐标转换为 A1 字符串
    return _convert_coords(result)
