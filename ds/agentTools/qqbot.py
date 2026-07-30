#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 02:12
# @Author  : Wu_RH
# @FileName: qqbot.py
import json
import time
import urllib
from datetime import datetime

import requests

from ds.agentTools import TOOLS
from ds.config import config


# ---- 工具函数辅助 ----
def format_message_list(messages, limit, reply_id):
    if not messages:
        return "没有消息。"
    recent = messages[-limit:]
    lines = []
    for msg in recent:
        user_id = msg.get('user_id') or msg.get('sender', {}).get('user_id')
        card = msg.get('sender', {}).get('card', '')
        nickname = msg.get('sender', {}).get('nickname', '')
        if card and nickname:
            display_name = card if card == nickname else f"{card}({nickname})"
        elif card:
            display_name = card
        elif nickname:
            display_name = nickname
        else:
            display_name = f"QQ {user_id}"
        if user_id:
            display_name += f"({user_id})"

        time_str = ""
        if 'time' in msg:
            dt = datetime.fromtimestamp(msg['time'])
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        # 消息内容
        segments = msg.get('message', [])
        if isinstance(segments, str):
            text = segments.strip() or "[非文本消息]"
            prefix = "🤖 [回复Bot] " if reply_id and str(msg.get('message_id')) == str(reply_id) else ""
            lines.append(f"[{time_str}] {prefix}{display_name}: {text}")
            continue

        # 处理reply
        reply_quote = ""
        reply_seg = None
        for seg in segments:
            if seg.get('type') == 'reply':
                reply_seg = seg
                break
        if reply_seg:
            data = reply_seg.get('data', {})
            sender_name = data.get('sender', {}).get('nickname') or data.get('sender', {}).get('card') or data.get('qq',
                                                                                                                   '未知用户')
            reply_text = data.get('text', '') or data.get('content', '')
            if len(reply_text) > 50:
                reply_text = reply_text[:50] + "…"
            if reply_text:
                reply_quote = f"↩️ 回复 @{sender_name}: “{reply_text}” "
            else:
                reply_quote = f"↩️ 回复 @{sender_name} 的消息 "

        # 提取文本
        text_parts = [seg.get('data', {}).get('text', '') for seg in segments if seg.get('type') == 'text']
        text_content = "".join(text_parts).strip()

        type_map = {
            'image': '图片', 'face': '表情', 'record': '语音',
            'video': '视频', 'file': '文件', 'json': '卡片',
            'music': '音乐', 'dice': '骰子', 'rps': '猜拳'
        }
        non_text = [f"[{type_map.get(seg['type'], seg['type'])}]" for seg in segments if
                    seg['type'] not in ('text', 'reply')]

        if text_content:
            content = text_content
            if non_text:
                content += " " + "".join(non_text)
        else:
            content = "".join(non_text) if non_text else "[非文本消息]"

        extra = "🤖 [回复Bot] " if reply_id and str(msg.get('message_id')) == str(reply_id) else ""
        lines.append(f"[{time_str}] {extra}{display_name}: {reply_quote}{content}")

    return "\n".join(lines)


# 17. get_group_msg
def tool_get_group_msg(group_id, count=20, reverseOrder=False):
    host = config["QQ_API_HOST"]
    port = config["QQ_API_PORT"]
    url = f"http://{host}:{port}/get_group_msg_history"
    payload = {
        "group_id": group_id,
        "count": count,
        "reverseOrder": reverseOrder,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get('status') == 'ok':
            messages = data.get('data', [])
            if isinstance(messages, dict) and 'messages' in messages:
                messages = messages['messages']
            if not isinstance(messages, list):
                return "❌ 获取到的历史消息格式异常。"
            formatted = format_message_list(messages, len(messages), None)
            return f"📜 群消息历史（最近 {len(messages)} 条）：\n{formatted}"
        else:
            return f"❌ 获取历史失败: {data}"
    except Exception as e:
        return f"❌ 获取群消息历史失败: {e}"


TOOLS["get_group_msg"] = {
    "description": "获取指定QQ群的近期消息历史，返回格式化的消息列表。",
    "parameters": {
        "group_id": {"type": "string", "required": True, "description": "目标群号"},
        "count": {"type": "number", "required": False, "description": "获取的消息数量，默认20"},
        "reverseOrder": {"type": "boolean", "required": False, "description": "是否按时间倒序（最新的在前），默认false"},
    },
    "execute": tool_get_group_msg,
}


# 18. send_group_msg

def tool_send_group_msg(
    group_id,
    text,
    at_user=None,
    timeout=None,
    history_limit=10
):
    host = config["QQ_API_HOST"]
    port = config["QQ_API_PORT"]
    poll_interval = config["QQ_POLL_INTERVAL"]  # 秒
    timeout_sec = (timeout or config["QQ_POLL_TIMEOUT"]) * 60  # 转秒

    # 1. 构造消息段
    segments = []
    if at_user:
        segments.append({"type": "at", "data": {"qq": at_user}})
        segments.append({"type": "text", "data": {"text": " " + text}})
    else:
        segments.append({"type": "text", "data": {"text": text}})

    send_url = f"http://{host}:{port}/send_group_msg"
    try:
        send_resp = requests.post(send_url, json={"group_id": group_id, "message": segments}, timeout=10)
        send_data = send_resp.json()
        if send_data.get('status') != 'ok':
            return f"❌ 发送失败: {send_data}"
        message_id = send_data.get('data', {}).get('message_id')
        if not message_id:
            return "❌ 响应中未包含 message_id"
    except Exception as e:
        return f"❌ 发送消息失败: {e}"

    # 2. 轮询历史消息
    all_messages = []
    seen_ids = set()
    deadline = time.time() + timeout_sec
    reply_msg = None

    history_url = f"http://{host}:{port}/get_group_msg_history"

    while time.time() < deadline:
        time.sleep(poll_interval)
        try:
            hist_resp = requests.post(
                history_url,
                json={"group_id": group_id, "count": 5, "reverseOrder": False},
                timeout=10
            )
            data = hist_resp.json()
            if data.get('status') != 'ok':
                continue

            messages = data.get('data', [])
            if isinstance(messages, dict) and 'messages' in messages:
                messages = messages['messages']
            if not isinstance(messages, list):
                continue

            # 记录新消息
            for msg in messages:
                if msg.get('message_id') not in seen_ids:
                    seen_ids.add(msg.get('message_id'))
                    all_messages.append(msg)

            # 检查是否有针对我们发送消息的回复
            for msg in reversed(messages):
                if msg.get('message_type') != 'group':
                    continue
                msg_segments = msg.get('message', [])
                for seg in msg_segments:
                    if seg.get('type') == 'reply' and str(seg.get('data', {}).get('id')) == str(message_id):
                        reply_msg = msg
                        break
                if reply_msg:
                    break
            if reply_msg:
                break
        except Exception:
            continue

    # 3. 返回结果
    if reply_msg:
        formatted = format_message_list(all_messages, history_limit, reply_msg.get('message_id'))
        count = min(history_limit, len(all_messages))
        return f"💬 收到回复！以下是最近 {count} 条消息：\n{formatted}"
    else:
        if not all_messages:
            return "⏰ 超时，且未收到任何消息。"
        formatted = format_message_list(all_messages, history_limit, None)
        count = min(history_limit, len(all_messages))
        return f"⏰ 无人回复，超时。以下是最近 {count} 条消息：\n{formatted}"


TOOLS["send_group_msg"] = {
    "description": "向指定QQ群发送消息，并等待群友回复（@可选）。若超时无人回复，则返回这段时间内的最近消息列表。",
    "parameters": {
        "group_id": {"type": "string", "required": True, "description": "目标群号"},
        "text": {"type": "string", "required": True, "description": "要发送的文本内容"},
        "at_user": {"type": "string", "required": False, "description": "要@的QQ号（可选）"},
        "timeout": {"type": "number", "required": False, "description": "等待回复的超时分钟数"},
        "history_limit": {"type": "number", "required": False, "description": "超时时返回的最大历史消息条数（默认10）"},
    },
    "execute": tool_send_group_msg,
}
