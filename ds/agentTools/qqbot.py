#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 02:12
# @Author  : Wu_RH
# @FileName: qqbot.py
import json
import time
from datetime import datetime

import requests

from ds.agentTools import TOOLS
from ds.config import config


# ---- 工具函数辅助 ----
def fetch_message_by_id(message_id):
    """调用 /get_msg 接口获取单条消息完整内容"""
    host = config["QQ_API_HOST"]
    port = config["QQ_API_PORT"]
    try:
        resp = requests.post(
            f"http://{host}:{port}/get_msg",
            json={"message_id": message_id},
            timeout=10
        )
        data = resp.json()
        if data.get('status') == 'ok':
            return data.get('data')
    except:
        pass
    return None


def get_msg(message_id):
    """
    调用 /get_msg 接口获取单条消息的完整数据。
    返回消息数据（dict）或 None。
    """
    host = config["QQ_API_HOST"]
    port = config["QQ_API_PORT"]
    try:
        resp = requests.post(
            f"http://{host}:{port}/get_msg",
            json={"message_id": message_id},
            timeout=10
        )
        data = resp.json()
        if data.get('status') == 'ok':
            return data.get('data')
    except:
        pass
    return None


def get_reply_chain(message_id, depth=20, _seen=None):
    """返回嵌套 JSON：{"message": {...}, "reply_to": {...}}"""
    if _seen is None:
        _seen = set()
    if not message_id or depth <= 0 or message_id in _seen:
        return None
    _seen.add(message_id)

    msg = get_msg(message_id)
    if not msg:
        return None

    child_id = None
    for seg in msg.get('message', []):
        if seg.get('type') == 'reply':
            child_id = seg.get('data', {}).get('id')
            break

    return {
        "message": msg,
        "reply_to": get_reply_chain(child_id, depth-1, _seen) if child_id else None
    }


def _format_chain_node(chain_node):
    """
    递归遍历回复链 JSON，生成带缩进的文本。
    不调用 format_message_list，只处理 JSON 结构。
    """
    if not chain_node:
        return ""

    parts = []
    level = 0
    current = chain_node

    while current:
        msg_data = current.get("message")
        if not msg_data:
            break

        # 复制消息数据，移除里面的 reply 节点（避免 format_message_list 递归）
        clean_msg = msg_data.copy()
        clean_msg["message"] = [
            seg for seg in clean_msg.get("message", [])
            if seg.get("type") != "reply"
        ]

        # 格式化清理后的消息（depth=0 确保不处理回复）
        msg_text = format_message_list([clean_msg], 1, None)
        indent = "    " * level
        indented = "\n    ".join(msg_text.splitlines())

        parts.append(f"{indent}↩️ 回复了: {indented}")

        # 移到下一层
        current = current.get("reply_to")
        level += 1

    return "\n".join(parts)


def format_message_list(messages, limit, reply_id=None):
    """
    将消息列表格式化为人类可读的文本，保持原始消息段顺序。
    完整解析 sender、message 数组中的所有字段。
    """
    if not messages:
        return "没有消息。"

    recent = messages[-limit:] if limit > 0 else messages
    lines = []

    for msg in recent:
        # ---- 1. 提取发送者信息 ----
        sender = msg.get('sender', {})
        user_id = msg.get('user_id') or sender.get('user_id')
        nickname = sender.get('nickname', '')
        card = sender.get('card', '')
        role = sender.get('role', '')
        self_id = msg.get('self_id')  # 机器人自己的QQ号

        # 构建显示名：全部显示（群名片、QQ昵称、QQ号）
        name_parts = []
        if card:
            name_parts.append(card)
        if nickname and nickname != card:
            name_parts.append(nickname)
        elif nickname and nickname == card:
            # 即使相同也加上，用括号区分（用户要求全部加上）
            name_parts.append(nickname)
        if user_id:
            name_parts.append(str(user_id))
        if not name_parts:
            name_parts.append("未知用户")

        # 用括号连接各部分，格式：card(nickname)(user_id)
        display_name = "".join([f"({part})" if i > 0 or not card else part for i, part in enumerate(name_parts)])
        # 如果 card 存在，则 card 不加括号；后续加括号
        # 但上面的表达式复杂，简单重写：
        display_name = ""
        if card:
            display_name += card
        if nickname:
            display_name += f"({nickname})"
        if user_id:
            display_name += f"({user_id})"
        if not display_name:
            display_name = "未知用户"

        # 如果 self_id 匹配，加 [我] 前缀（保留）
        if self_id and str(user_id) == str(self_id):
            display_name = f"[我] {display_name}"
        # 如果 role 存在，追加角色（保留）
        if role:
            role_map = {'admin': '管理员', 'owner': '群主', 'member': '成员'}
            display_name = f"{display_name}[{role_map.get(role, role)}]"

        # ---- 2. 时间 ----
        time_str = ""
        if 'time' in msg:
            dt = datetime.fromtimestamp(msg['time'])
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        # ---- 3. 处理消息段，按原始顺序 ----
        segments = msg.get('message', [])
        if isinstance(segments, str):
            # 兼容纯文本格式
            text = segments.strip() or "[非文本消息]"
            prefix = "🤖 [回复Bot] " if reply_id and str(msg.get('message_id')) == str(reply_id) else ""
            lines.append(f"[{time_str}] {prefix}{display_name}: {text}")
            continue

        parts = []
        for seg in segments:
            seg_type = seg.get('type')
            data = seg.get('data', {})

            if seg_type == 'text':
                parts.append(data.get('text', ''))

            elif seg_type == 'at':
                qq = data.get('qq', '')
                name = data.get('name', '')
                parts.append(f"@{name}({qq})" if name else f"@{qq}")

            elif seg_type == 'reply':
                reply_msg_id = data.get('id', '')
                if not reply_msg_id:
                    parts.append("[无效回复]")
                    continue

                chain = {
                    "message": msg,
                    "reply_to": get_reply_chain(reply_msg_id),
                }
                if not chain:
                    parts.append("[获取回复失败]")
                    continue

                parts = ["回复消息栈: \n" + _format_chain_node(chain)]
                break

            elif seg_type == 'image':
                file = data.get('file', '')
                url = data.get('url', '')
                if url:
                    parts.append(f"[图片: {url[:80]}{'...' if len(url) > 80 else ''}]")
                elif file:
                    parts.append(f"[图片: {file[:80]}{'...' if len(file) > 80 else ''}]")
                else:
                    parts.append("[图片]")

            elif seg_type == 'face':
                face_id = data.get('id', '')
                face_name = data.get('name', '')
                parts.append(f"[表情: {face_name}]" if face_name else f"[表情:{face_id}]")

            elif seg_type == 'record':
                file = data.get('file', '')
                parts.append(f"[语音: {file[:80]}{'...' if len(file) > 80 else ''}]" if file else "[语音]")

            elif seg_type == 'video':
                file = data.get('file', '')
                parts.append(f"[视频: {file[:80]}{'...' if len(file) > 80 else ''}]" if file else "[视频]")

            elif seg_type == 'file':
                file_name = data.get('name', '')
                file_size = data.get('size', '')
                if file_name and file_size:
                    parts.append(f"[文件: {file_name} ({file_size}B)]")
                elif file_name:
                    parts.append(f"[文件: {file_name}]")
                else:
                    parts.append("[文件]")

            elif seg_type == 'json':
                parts.append("[卡片消息]")

            elif seg_type == 'music':
                music_type = data.get('type', '')
                title = data.get('title', '')
                music_id = data.get('id', '')
                url = data.get('url', '')
                audio = data.get('audio', '')
                image = data.get('image', '')

                if music_type in ('qq', '163'):
                    # 标准音乐（QQ/网易云）
                    if title:
                        parts.append(f"[音乐 {music_type}: {title} (ID: {music_id})]")
                    else:
                        parts.append(f"[音乐 {music_type}: ID {music_id}]")
                elif music_type == 'custom':
                    # 自定义音乐（分享链接）
                    info = []
                    if title:
                        info.append(f"标题: {title}")
                    if url:
                        info.append(f"链接: {url[:60]}{'...' if len(url) > 60 else ''}")
                    if audio:
                        info.append(f"音频: {audio[:30]}{'...' if len(audio) > 30 else ''}")
                    if image:
                        info.append(f"封面: {image[:30]}{'...' if len(image) > 30 else ''}")
                    parts.append(f"[自定义音乐: {' | '.join(info)}]")
                else:
                    # 未知格式，保留完整 JSON 以防丢失信息
                    parts.append(f"[音乐: {json.dumps(data, ensure_ascii=False)}]")

            elif seg_type == 'dice':
                value = data.get('value', '')
                parts.append(f"[骰子: {value}]")

            elif seg_type == 'rps':
                value = data.get('value', '')
                parts.append(f"[猜拳: {value}]")

            elif seg_type == 'location':
                lat = data.get('lat', '')
                lng = data.get('lng', '')
                title = data.get('title', '')
                if title:
                    parts.append(f"[位置: {title}]")
                else:
                    parts.append(f"[位置: {lat},{lng}]")

            elif seg_type == 'redbag':
                title = data.get('title', '')
                parts.append(f"[红包: {title}]" if title else "[红包]")

            elif seg_type == 'forward':
                parts.append("[转发消息]")

            elif seg_type == 'node':
                parts.append("[合并转发]")

            elif seg_type == 'xml':
                parts.append("[XML消息]")

            elif seg_type == 'gift':
                parts.append("[礼物]")

            elif seg_type == 'poke':
                parts.append("[戳一戳]")

            else:
                parts.append(f"[未知类型: {json.dumps(seg, ensure_ascii=False)}]")

        # ---- 4. 合并所有段 ----
        content = ''.join(parts).strip()
        if not content:
            content = "[空消息]"

        # 标记是否为回复Bot的消息
        prefix = "🤖 [回复Bot] " if reply_id and str(msg.get('message_id')) == str(reply_id) else ""
        lines.append(f"[{time_str}] {prefix}{display_name}: {content}")

    return "\n".join(lines)


def _get_bot_qq():
    """从 QQ API 获取当前登录机器人的 QQ 号，缓存结果"""
    if hasattr(_get_bot_qq, "_cache"):
        return _get_bot_qq.cache

    host = config["QQ_API_HOST"]
    port = config["QQ_API_PORT"]
    try:
        resp = requests.get(f"http://{host}:{port}/get_login_info", timeout=5)
        data = resp.json()
        if data.get('status') == 'ok':
            qq = str(data.get('data', {}).get('user_id', ''))
            _get_bot_qq.cache = qq
            return qq
    except:
        pass
    return ""


# 17. get_group_msg
def tool_listen_group_msg(
    group_id: str,
    trigger: str = 'any',
    keyword: str = None,
    timeout: int = 5,
    history_limit: int = 5,
    fetch_count: int = 10
):
    """
    监听群消息，阻塞直到触发条件满足或超时，返回最新的 history_limit 条消息。
    trigger: any(任意消息) | mention(@机器人) | keyword(含关键词)
    timeout: 分钟，默认5
    history_limit: 返回消息条数，默认5
    """
    host = config["QQ_API_HOST"]
    port = config["QQ_API_PORT"]
    poll_interval = config["QQ_POLL_INTERVAL"]  # 秒
    bot_qq = _get_bot_qq()
    fetch_count = history_limit if history_limit > fetch_count else fetch_count

    if trigger == 'keyword' and not keyword:
        return "❌ trigger='keyword' 时必须提供 keyword"

    def fetch_messages(count):
        try:
            resp = requests.post(
                f"http://{host}:{port}/get_group_msg_history",
                json={"group_id": group_id, "count": count, "reverseOrder": False},
                timeout=10
            )
            data = resp.json()
            if data.get('status') != 'ok':
                return []
            msgs = data.get('data', {}).get('messages', [])
            return msgs if isinstance(msgs, list) else []
        except:
            return []

    def is_triggered(message):
        if not message or message.get('message_type') != 'group':
            return False
        if trigger == 'any':
            return True
        if trigger == 'mention':
            if not bot_qq:
                return False
            for seg in message.get('message', []):
                if seg.get('type') == 'at' and str(seg.get('data', {}).get('qq')) == str(bot_qq):
                    return True
            return False
        if trigger == 'keyword':
            text_parts = [
                seg.get('data', {}).get('text', '')
                for seg in message.get('message', [])
                if seg.get('type') == 'text'
            ]
            full_text = ''.join(text_parts).lower()
            return keyword.lower() in full_text
        return False

    start_time = time.time()
    timeout_sec = timeout * 60
    seen_ids = set()

    # 首次拉取，初始化已读
    initial_msgs = fetch_messages(fetch_count)
    for m in initial_msgs:
        seen_ids.add(m.get('message_id'))

    while time.time() - start_time < timeout_sec:
        time.sleep(poll_interval)
        msgs = fetch_messages(fetch_count)
        if not msgs:
            continue

        for msg in reversed(msgs):
            msg_id = msg.get('message_id')
            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)

            if is_triggered(msg):
                # 触发：直接拉取最新的 history_limit 条消息返回
                result_msgs = fetch_messages(history_limit)
                if result_msgs:
                    formatted = format_message_list(result_msgs, len(result_msgs), None)
                    return f"📨 触发条件满足！最新的 {len(result_msgs)} 条消息：\n{formatted}"
                else:
                    return "📨 触发条件满足，但拉取消息失败。"

    # 超时
    result_msgs = fetch_messages(history_limit)
    if result_msgs:
        formatted = format_message_list(result_msgs, len(result_msgs), None)
        return f"⏰ 监听超时 ({timeout}分钟)，最新的 {len(result_msgs)} 条消息：\n{formatted}"
    else:
        return f"⏰ 监听超时 ({timeout}分钟)，未收到任何消息。"


TOOLS["listen_group_msg"] = {
    "description": "监听群消息，触发时返回累积新消息的末尾 history_limit 条（格式化文本）。每次轮询最多拉取 fetch_count 条。",
    "parameters": {
        "group_id": {"type": "string", "required": True, "description": "群号"},
        "trigger": {"type": "string", "required": False, "description": "触发类型：'any'、'mention'、'keyword'，默认'any'"},
        "keyword": {"type": "string", "required": False, "description": "trigger='keyword' 时必填"},
        "timeout": {"type": "number", "required": False, "description": "监听超时时间，单位分钟，默认5"},
        "history_limit": {"type": "number", "required": False, "description": "返回消息条数上限（取最新的 N 条），默认5"},
        "fetch_count": {"type": "number", "required": False, "description": "每次轮询拉取的最大条数，默认50"},
    },
    "execute": tool_listen_group_msg,
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


if __name__ == "__main__":
    # ─── 真实监听测试（需要 API 服务运行）───
    GROUP_ID = "1051027867"
    print(f"开始监听群 {GROUP_ID}")
    result = tool_listen_group_msg(
        group_id=GROUP_ID,
        trigger='keyword',
        keyword="1",
        timeout=0,          # 2分钟，够你发消息了
        history_limit=100
    )
    print("\n监听结果：")
    print(result)
