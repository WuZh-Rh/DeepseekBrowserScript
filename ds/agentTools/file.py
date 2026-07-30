#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 02:14
# @Author  : Wu_RH
# @FileName: file.py
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import requests

from ds.agentTools import TOOLS
from ds.config import config


def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def resolve_path(file_path):
    p = Path(file_path)
    if p.is_absolute():
        return str(p)
    return str(Path(config["WORKING_DIR"]) / p)


def truncate(s, max_len=None):
    if max_len is None:
        max_len = config["MAX_OUTPUT_LENGTH"]
    s = str(s)
    if len(s) <= max_len:
        return s
    half = max_len // 2
    return s[:half] + f"\n\n⚠ [输出已截断 — 共 {len(s):,} 字符，仅显示开头和结尾各 {half} 字符]\n\n" + s[-half:]


# 1. read_file
def tool_read_file(path, start_line=None, end_line=None):
    abs_path = resolve_path(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"文件不存在：{path}")
    if os.path.isdir(abs_path):
        raise IsADirectoryError(f"{path} 是一个目录")
    with open(abs_path, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.splitlines()
    if start_line is not None or end_line is not None:
        s = max(0, (start_line or 1) - 1)
        e = end_line if end_line is not None else len(lines)
        selected = lines[s:e]
        numbered = "\n".join(f"{s + i + 1}: {l}" for i, l in enumerate(selected))
        return f"[{path} | 行 {s + 1}–{e}]\n{truncate(numbered)}"
    line_count = len(lines)
    if line_count <= 300:
        numbered = "\n".join(f"{i + 1}: {l}" for i, l in enumerate(lines))
        return f"[{path} | {line_count} 行]\n{numbered}"
    return f"[{path} | {line_count} 行 — 可使用 start_line/end_line 分段读取]\n{truncate(content)}"


TOOLS["read_file"] = {
    "description": "读取文件的全部内容，也可按行号范围读取。",
    "parameters": {
        "path": {"type": "string", "required": True, "description": "文件路径"},
        "start_line": {"type": "number", "required": False, "description": "起始行号（从 1 开始）"},
        "end_line": {"type": "number", "required": False, "description": "结束行号（包含）"},
    },
    "execute": tool_read_file,
}


# 2. write_file
def tool_write_file(path, content):
    abs_path = resolve_path(path)
    Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)
    size = len(content.encode('utf-8'))
    line_count = content.count('\n') + 1
    return f"✓ 已写入 {format_bytes(size)}（{line_count} 行）→ {path}"


TOOLS["write_file"] = {
    "description": "将内容写入文件（覆盖已存在的文件），自动创建父目录。",
    "parameters": {
        "path": {"type": "string", "required": True, "description": "目标文件路径"},
        "content": {"type": "string", "required": True, "description": "要写入的完整内容"},
    },
    "execute": tool_write_file,
}


# 3. append_to_file
def tool_append_to_file(path, content):
    abs_path = resolve_path(path)
    Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
    with open(abs_path, 'a', encoding='utf-8') as f:
        f.write(content)
    size = len(content.encode('utf-8'))
    return f"✓ 已追加 {format_bytes(size)} 到 {path}"


TOOLS["append_to_file"] = {
    "description": "将文本追加到文件末尾（若文件不存在则创建）。",
    "parameters": {
        "path": {"type": "string", "required": True, "description": "文件路径"},
        "content": {"type": "string", "required": True, "description": "要追加的文本"},
    },
    "execute": tool_append_to_file,
}


# 4. replace_in_file
def tool_replace_in_file(path, find, replace, use_regex=False, all_occurrences=True):
    abs_path = resolve_path(path)
    with open(abs_path, 'r', encoding='utf-8') as f:
        original = f.read()
    if use_regex:
        flag = re.MULTILINE
        if all_occurrences:
            flag |= re.DOTALL  # 使得 . 匹配换行
        new_content = re.sub(find, replace, original, flags=flag)
    else:
        if all_occurrences:
            new_content = original.replace(find, replace)
        else:
            new_content = original.replace(find, replace, 1)
    if new_content == original:
        return f"⚠ 在 {path} 中未找到 \"{find}\""
    count = original.count(find) if not use_regex else len(re.findall(find, original))
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return f"✓ 已在 {path} 中替换了 {count} 处 \"{find}\""


TOOLS["replace_in_file"] = {
    "description": "在文件中查找并替换文本，支持正则表达式。",
    "parameters": {
        "path": {"type": "string", "required": True, "description": "文件路径"},
        "find": {"type": "string", "required": True, "description": "要查找的文本"},
        "replace": {"type": "string", "required": True, "description": "替换后的文本"},
        "use_regex": {"type": "boolean", "required": False, "description": "将 find 视为正则表达式（默认：false）"},
        "all_occurrences": {"type": "boolean", "required": False, "description": "替换所有匹配项（默认：true）"},
    },
    "execute": tool_replace_in_file,
}


# 5. delete_file
def tool_delete_file(path):
    abs_path = resolve_path(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"文件不存在：{path}")
    os.unlink(abs_path)
    return f"✓ 已删除 {path}"


TOOLS["delete_file"] = {
    "description": "永久删除文件。",
    "parameters": {"path": {"type": "string", "required": True, "description": "要删除的文件路径"}},
    "execute": tool_delete_file,
}


# 6. list_directory
def tool_list_directory(path=".", recursive=False, show_hidden=False):
    abs_path = resolve_path(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"目录不存在：{path}")
    if not os.path.isdir(abs_path):
        raise NotADirectoryError(f"{path} 不是目录")

    if recursive:
        exclude_dirs = {'node_modules', '.git', 'dist', '.next', 'build', '__pycache__'}
        results = []
        for root, dirs, files in os.walk(abs_path):
            # 限制深度3
            depth = root[len(abs_path):].count(os.sep)
            if depth > 3:
                continue
            # 排除目录
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            rel_root = os.path.relpath(root, abs_path)
            if rel_root != '.':
                results.append(f"📁  {rel_root}/")
            for f in files:
                if not show_hidden and f.startswith('.'):
                    continue
                full = os.path.join(root, f)
                size = format_bytes(os.path.getsize(full)) if os.path.isfile(full) else ""
                results.append(f"📄  {os.path.join(str(rel_root), f)}  {size}")
            if len(results) > 300:
                results = results[:300]
                break
        if not results:
            return "(空)"
        return "\n".join(results)
    else:
        entries = os.listdir(abs_path)
        if not show_hidden:
            entries = [e for e in entries if not e.startswith('.')]
        entries.sort(key=lambda x: (not os.path.isdir(os.path.join(abs_path, x)), x.lower()))
        lines = []
        for e in entries:
            full = os.path.join(abs_path, e)
            if os.path.isdir(full):
                lines.append(f"📁  {e}/")
            else:
                size = format_bytes(os.path.getsize(full))
                lines.append(f"📄  {e}  {size}")
        if not lines:
            return f"(目录为空：{path})"
        return f"[{path}] — {len(lines)} 个项目\n" + "\n".join(lines)


TOOLS["list_directory"] = {
    "description": "列出目录中的文件和文件夹，可选择递归列出子目录。",
    "parameters": {
        "path": {"type": "string", "required": False, "description": "要列出的目录（默认为工作目录）"},
        "recursive": {"type": "boolean", "required": False, "description": "是否递归子目录（默认：false）"},
        "show_hidden": {"type": "boolean", "required": False, "description": "是否显示以 . 开头的隐藏文件（默认：false）"},
    },
    "execute": tool_list_directory,
}


# 7. create_directory
def tool_create_directory(path):
    abs_path = resolve_path(path)
    Path(abs_path).mkdir(parents=True, exist_ok=True)
    return f"✓ 已创建目录：{path}"


TOOLS["create_directory"] = {
    "description": "创建目录（包括所有必要的父目录）。",
    "parameters": {"path": {"type": "string", "required": True, "description": "要创建的目录路径"}},
    "execute": tool_create_directory,
}


# 8. move_file
def tool_move_file(source, destination):
    src = resolve_path(source)
    dst = resolve_path(destination)
    if not os.path.exists(src):
        raise FileNotFoundError(f"源文件不存在：{source}")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)
    return f"✓ 已移动：{source} → {destination}"


TOOLS["move_file"] = {
    "description": "移动或重命名文件/目录。",
    "parameters": {
        "source": {"type": "string", "required": True, "description": "源路径"},
        "destination": {"type": "string", "required": True, "description": "目标路径"},
    },
    "execute": tool_move_file,
}


# 9. copy_file
def tool_copy_file(source, destination):
    src = resolve_path(source)
    dst = resolve_path(destination)
    if not os.path.exists(src):
        raise FileNotFoundError(f"源文件不存在：{source}")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"✓ 已复制：{source} → {destination}"


TOOLS["copy_file"] = {
    "description": "复制文件到新位置。",
    "parameters": {
        "source": {"type": "string", "required": True, "description": "源文件路径"},
        "destination": {"type": "string", "required": True, "description": "目标文件路径"},
    },
    "execute": tool_copy_file,
}


# 10. get_file_info
def tool_get_file_info(path):
    abs_path = resolve_path(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"未找到：{path}")
    stat = os.stat(abs_path)
    info = {
        "path": abs_path,
        "type": "目录" if os.path.isdir(abs_path) else "文件",
        "size": stat.st_size,
        "size_human": format_bytes(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "permissions": oct(stat.st_mode)[-3:],
    }
    if os.path.isfile(abs_path):
        with open(abs_path, 'r', encoding='utf-8') as f:
            info["lines"] = f.read().count('\n') + 1
        info["encoding"] = "utf-8"
    return json.dumps(info, indent=2, ensure_ascii=False)


TOOLS["get_file_info"] = {
    "description": "获取文件或目录的元数据（大小、修改时间、行数等）。",
    "parameters": {"path": {"type": "string", "required": True, "description": "文件或目录路径"}},
    "execute": tool_get_file_info,
}


# 12. find_files
def tool_find_files(pattern, directory=".", exclude=None):
    root = resolve_path(directory)
    if not os.path.exists(root):
        raise FileNotFoundError(f"目录不存在：{directory}")
    exclude_dirs = {'node_modules', '.git', 'dist', '.next', 'build', '__pycache__'}
    # 将glob转正则
    regex = re.compile('^' + re.escape(pattern).replace('\\*', '.*').replace('\\?', '.') + '$')
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for f in filenames:
            if regex.match(f):
                full = os.path.join(dirpath, f)
                if exclude and exclude in full:
                    continue
                results.append(full)
                if len(results) >= 100:
                    break
        if len(results) >= 100:
            break
    if not results:
        return f"在 {directory} 中未找到匹配 \"{pattern}\" 的文件"
    return "\n".join([str(result_str) for result_str in results])


TOOLS["find_files"] = {
    "description": "按文件名模式搜索文件（支持 glob 风格，例如 '*.js'）。",
    "parameters": {
        "pattern": {"type": "string", "required": True, "description": "文件名模式"},
        "directory": {"type": "string", "required": False, "description": "搜索的目录（默认为工作目录）"},
        "exclude": {"type": "string", "required": False, "description": "排除包含该子字符串的路径"},
    },
    "execute": tool_find_files,
}


# 13. search_in_files
def tool_search_in_files(pattern, directory=".", file_pattern=None, case_sensitive=False, context_lines=2):
    root = resolve_path(directory)
    if not os.path.exists(root):
        raise FileNotFoundError(f"目录不存在：{directory}")
    exclude_dirs = {'node_modules', '.git', 'dist', '.next', 'build', '__pycache__'}
    file_regex = None
    if file_pattern:
        file_regex = re.compile('^' + re.escape(file_pattern).replace('\\*', '.*') + '$')
    flags = 0 if case_sensitive else re.I
    try:
        search_re = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"正则表达式无效：{e}")
    matches = []
    max_matches = 150
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for f in filenames:
            if file_regex and not file_regex.match(f):
                continue
            full = os.path.join(dirpath, f)
            try:
                if os.path.getsize(full) > 2 * 1024 * 1024:
                    continue
                with open(full, 'r', encoding='utf-8', errors='ignore') as fp:
                    lines = fp.readlines()
            except:
                continue
            for i, line in enumerate(lines):
                if search_re.search(line):
                    # start = max(0, i - context_lines)
                    # end = min(len(lines), i + context_lines + 1)
                    # context = "\n".join(f"{idx + 1}: {lines[idx].rstrip()}" for idx in range(start, end))
                    # matches.append(f"{full}:{i + 1} 附近:\n{context}")
                    matches.append(f"{full}:{i + 1}: {line.strip()}")
                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break
        if len(matches) >= max_matches:
            break
    if not matches:
        return f"未找到匹配 \"{pattern}\" 的内容"
    return truncate("\n".join(matches))


TOOLS["search_in_files"] = {
    "description": "在文件内容中搜索文本模式（类似 grep -r），返回匹配行及文件名。",
    "parameters": {
        "pattern": {"type": "string", "required": True, "description": "要搜索的文本或正则表达式"},
        "directory": {"type": "string", "required": False, "description": "搜索目录（默认为工作目录）"},
        "file_pattern": {"type": "string", "required": False, "description": "仅搜索匹配此模式的文件"},
        "case_sensitive": {"type": "boolean", "required": False, "description": "是否区分大小写（默认：false）"},
        "context_lines": {"type": "number", "required": False, "description": "匹配行周围的上下文行数（默认：2）"},
    },
    "execute": tool_search_in_files,
}


# 14. read_url
def tool_read_url(url):
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; DeepSeekAgent/1.0)'}
        )
        resp.encoding = 'utf-8'
        data = resp.text
        # 剥离HTML标签
        text = re.sub(r'<script[\s\S]*?</script>', '', data, flags=re.I)
        text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s{3,}', '\n\n', text).strip()
        return truncate(text)
    except Exception as e:
        raise RuntimeError(f"URL 获取失败: {e}")


TOOLS["read_url"] = {
    "description": "获取 URL 的文本内容（适用于阅读文档、API 等）。",
    "parameters": {"url": {"type": "string", "required": True, "description": "要获取的完整 URL"}},
    "execute": tool_read_url,
}


# 15. write_files
def tool_write_files(files):
    if not isinstance(files, list):
        raise ValueError('"files" 必须为 {path, content} 数组')
    results = []
    for item in files:
        path = item.get('path')
        content = item.get('content')
        if not path or content is None:
            continue
        abs_path = resolve_path(path)
        Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        results.append(f"✓ {path}")
    return f"已写入 {len(results)} 个文件：\n" + "\n".join(results)


TOOLS["write_files"] = {
    "description": "一次性写入多个文件 —— 适用于项目脚手架搭建。",
    "parameters": {
        "files": {"type": "array", "required": True, "description": "{path, content} 对象的数组"},
    },
    "execute": tool_write_files,
}
