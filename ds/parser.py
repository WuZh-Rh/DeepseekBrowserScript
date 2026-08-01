#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:45
# @Author  : Wu_RH
# @FileName: parser.py
# src/parser.py
import re
import json


def strip_thinking_blocks(text):
    text = re.sub(r'<think>[\s\S]*?<\/think>\n?', '', text, flags=re.I)
    text = re.sub(r'^Thinking\.{0,3}\n[\s\S]*?\n\n', '', text, flags=re.M)
    return text.strip()


def attempt_json_fix(s):
    try:
        fixed = re.sub(r',\s*([}\]])', r'\1', s)
        fixed = re.sub(r'([{,])\s*(\w+)\s*:', r'\1"\2":', fixed)
        return json.loads(fixed)
    except:
        return None


def extract_largest_json_object(text):
    best = None
    best_len = 0
    i = 0
    while i < len(text):
        if text[i] != '{':
            i += 1
            continue
        depth = 0
        in_str = False
        escape = False
        j = i
        while j < len(text):
            ch = text[j]
            if escape:
                escape = False
            elif ch == '\\' and in_str:
                escape = True
            elif ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[i:j + 1]
                        if len(candidate) > best_len:
                            try:
                                parsed = json.loads(candidate)
                                best = parsed
                                best_len = len(candidate)
                            except:
                                fixed = attempt_json_fix(candidate)
                                if fixed and len(candidate) > best_len:
                                    best = fixed
                                    best_len = len(candidate)
                        break
            j += 1
        i += 1
    return best


def parse_response(raw_text):
    text = strip_thinking_blocks(raw_text)

    # Strategy 0: bare "tool_call\n{...}"
    bare_match = re.match(r'^tool_call\s*\n([\s\S]+)$', text, re.I)
    if bare_match:
        json_raw = bare_match.group(1).strip()
        try:
            parsed = json.loads(json_raw)
            name = parsed.get('name') or parsed.get('tool') or parsed.get('function')
            args = parsed.get('args') or parsed.get('arguments') or parsed.get('parameters') or parsed.get(
                'input') or {}
            if name and isinstance(name, str):
                return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}
        except:
            fixed = attempt_json_fix(json_raw)
            if fixed:
                name = fixed.get('name') or fixed.get('tool') or fixed.get('function')
                args = fixed.get('args') or fixed.get('arguments') or fixed.get('parameters') or fixed.get(
                    'input') or {}
                if name:
                    return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}

    # Strategy 1: ```tool_call ...```
    fenced = re.search(r'```tool_call\s*([\s\S]*?)```', text, re.I)
    if fenced:
        raw = fenced.group(1).strip()
        try:
            parsed = json.loads(raw)
            name = parsed.get('name') or parsed.get('tool') or parsed.get('function')
            args = parsed.get('args') or parsed.get('arguments') or parsed.get('parameters') or parsed.get(
                'input') or {}
            if name and isinstance(name, str):
                return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}
        except Exception as e:
            fixed = attempt_json_fix(raw)
            if fixed:
                name = fixed.get('name') or fixed.get('tool') or fixed.get('function')
                args = fixed.get('args') or fixed.get('arguments') or fixed.get('parameters') or fixed.get(
                    'input') or {}
                if name:
                    return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}
            return {'type': 'error', 'message': f'tool_call block invalid JSON: {e}\nContent: {raw[:300]}',
                    'raw': raw_text}

    # Strategy 2: ```json ...```
    json_fence = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if json_fence:
        try:
            parsed = json.loads(json_fence.group(1))
            name = parsed.get('name') or parsed.get('tool') or parsed.get('function')
            args = parsed.get('args') or parsed.get('arguments') or parsed.get('parameters') or parsed.get(
                'input') or {}
            if name and isinstance(name, str):
                return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}
        except:
            pass

    # Strategy 3: XML <tool_call>
    xml_match = re.search(
        r'<tool_call[^>]*>\s*(?:<name>([\s\S]*?)</name>\s*)?(?:<input>([\s\S]*?)</input>|<args>([\s\S]*?)</args>)\s*</tool_call>',
        text, re.I)
    if xml_match:
        name = xml_match.group(1).strip() if xml_match.group(1) else None
        input_raw = (xml_match.group(2) or xml_match.group(3) or '').strip()
        if name:
            return _try_parse_tool_call(name, input_raw, raw_text)

    # Strategy 4: stripped XML
    stripped = re.search(r'tool_call\s+name\s+([\w_]+)\s*/name\s+input\s*([\s\S]*?)\s*/input\s*/tool_call', text, re.I)
    if stripped:
        name = stripped.group(1).strip()
        input_raw = stripped.group(2).strip()
        return _try_parse_tool_call(name, input_raw, raw_text)

    # Strategy 5: any JSON object with "name"
    if re.search(r'["\'](?:name|tool|function)["\']\s*:\s*["\'][\w_]+["\']', text):
        obj = extract_largest_json_object(text)
        if obj:
            name = obj.get('name') or obj.get('tool') or obj.get('function')
            args = obj.get('args') or obj.get('arguments') or obj.get('parameters') or obj.get('input') or {}
            if name and isinstance(name, str):
                return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}

    # Strategy 6: Python-style function call
    func_match = re.search(r'```\w*\s*([\w_]+)\(([^)]*)\)\s*```', text)
    if func_match:
        name = func_match.group(1)
        args_raw = func_match.group(2)
        args = {}
        for m in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|(\d+(?:\.\d+)?)|(\btrue\b|\bfalse\b))',
                             args_raw):
            key = m.group(1)
            if m.group(2) is not None:
                args[key] = m.group(2)
            elif m.group(3) is not None:
                args[key] = m.group(3)
            elif m.group(4) is not None:
                args[key] = float(m.group(4))
            elif m.group(5) is not None:
                args[key] = m.group(5).lower() == 'true'
        if args:
            return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}

    # No tool call -> final
    return {'type': 'final', 'content': text, 'raw': raw_text}


def _try_parse_tool_call(name, input_raw, raw_text):
    try:
        args = json.loads(input_raw)
        return {'type': 'tool_call', 'name': name, 'args': args, 'raw': raw_text}
    except Exception as e:
        fixed = attempt_json_fix(input_raw)
        if fixed is not None:
            return {'type': 'tool_call', 'name': name, 'args': fixed, 'raw': raw_text}
        return {
            'type': 'error',
            'message': f'Tool "{name}" invalid JSON: {e}\nRaw: {input_raw[:200]}',
            'raw': raw_text
        }


def format_tool_result(tool_name, result, is_error=False):
    status = "ERROR" if is_error else "SUCCESS"
    return f"[TOOL RESULT: {tool_name} | {status}]\n{result}\n[END TOOL RESULT]"


def is_asking_question(text):
    indicators = [
        r'\?(\s*$)',
        r'could you (please |kindly )?clarify',
        r'can you provide more',
        r'what (do you|would you) (want|like|prefer)',
        r'please (specify|clarify|tell me)',
    ]
    return any(re.search(p, text, re.I) for p in indicators)
