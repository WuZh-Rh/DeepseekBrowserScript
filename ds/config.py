#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:30
# @Author  : Wu_RH
# @FileName: config.py.py

import os
import json
from pathlib import Path

HOME = Path.home()
SELF_PATH = Path(os.path.abspath(__file__)).parent.parent

DEFAULT_CONFIG = {
    "DEEPSEEK_URL": "https://chat.deepseek.com",
    "SESSION_DIR": str(SELF_PATH / "session" / "session"),
    "HEADLESS": False,
    "RESPONSE_TIMEOUT": 180000,      # 毫秒
    "STABLE_DELAY": 2500,            # 毫秒
    "SEND_DELAY": 400,               # 毫秒
    "MAX_ITERATIONS": 300,
    "WORKING_DIR": os.getcwd(),
    "MAX_OUTPUT_LENGTH": 8000,
    "DEBUG": False,
    "QQ_API_HOST": "10.147.19.186",  # 请根据实际修改
    "QQ_API_PORT": 3000,
    "QQ_POLL_TIMEOUT": 180,          # 分钟
    "QQ_POLL_INTERVAL": 5,           # 秒
    "TEST_BAT_PATH": None,
}


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def get_config():
    config = DEFAULT_CONFIG.copy()
    global_cfg = load_json(HOME / ".deepseek-agent" / "config.json")
    project_cfg = load_json(Path.cwd() / "deepseek-agent.config.json")
    config.update(global_cfg)
    config.update(project_cfg)
    # 确保会话目录存在
    Path(config["SESSION_DIR"]).mkdir(parents=True, exist_ok=True)
    (HOME / ".deepseek-agent" / "logs").mkdir(parents=True, exist_ok=True)
    return config


CONFIG = get_config()
