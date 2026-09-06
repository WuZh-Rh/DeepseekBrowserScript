#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:55
# @Author  : Wu_RH
# @FileName: __main__.py

import sys
import os
import argparse
import signal
import traceback
from pathlib import Path
from typing import Optional

from ds.config import CONFIG
from ds import logger
from ds.logger import getLogger, Logger


LOGGER: Optional[Logger] = None

SELF_PATH = os.getcwd()


def parse_args():
    parser = argparse.ArgumentParser(
        description="DeepSeek 浏览器代理 — 通过浏览器自动化实现的 AI 编码代理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m ds "写一个 Hello World"
  python -m ds --interactive
  python -m ds --headless "构建项目"
  python -m ds --calibrate
        """
    )
    parser.add_argument("-t", "--task", help="要运行的任务（也可以不加标志直接写）")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互式 REPL 模式")
    parser.add_argument("-d", "--dir", "--work-dir", dest="working_dir", help="设置工作目录（默认当前目录）")
    parser.add_argument("--debug", action="store_true", help="输出详细的调试信息")
    parser.add_argument("--headless", action="store_true", help="无头模式运行浏览器")
    parser.add_argument("--test-bat", dest="test_bat", help="指定测试脚本（.bat），用于验证最终结果")
    parser.add_argument("--log-path", dest="log_path", help="指定日志目录", default="./logs")
    parser.add_argument("--roll-name", dest="roll_name",
                        help="滚动日志的时候添加的后缀(YYYY-MM-DD-XXXX-?.log)", default="")
    parser.add_argument("-m", "--max-iterations", type=int, help="限制 Agent 的最大循环轮数（默认 150）")
    parser.add_argument("-S", "--session-dir", dest="session_dir", help="指定会话目录", default="main")
    parser.add_argument("--deny-tools", nargs='+', help="禁用指定的工具，空格分隔", default=None)
    parser.add_argument("--ext-tools", nargs='+', help="扩展工具['wzq', ](默认不添加)", default=None)
    parser.add_argument("--mode", choices=["fast", "expert", "vision"], default="fast",
                        help="选择 DeepSeek 模式：fast（快速）, expert（专家）, vision（识图），默认 fast")
    parser.add_argument("--task-path", help="从文件读取任务内容")
    parser.add_argument("--load-file", help="上传/加载指定文件")
    parser.add_argument("rest", nargs="*", help="任务文本（不带 -t 时）")
    return parser.parse_args()


def main():
    global LOGGER
    args = parse_args()

    # 初始化日志
    if args.session_dir:
        temp_session_dir = Path(args.session_dir)
        if hasattr(args, "roll_name") and args.roll_name == "":
            args.roll_name = temp_session_dir.name

    if sys.platform == 'win32':
        if os.path.isabs(args.log_path):
            log_dir = args.log_path
        else:
            log_dir = os.path.join(Path(SELF_PATH), Path(args.log_path))
    else:
        log_dir = os.path.expanduser("~/.deepseek-agent/logs")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_name = "latest"
    if args.roll_name:
        log_name += "-" + args.roll_name
    log_name += ".log"
    log_file_path = str(log_dir / log_name)

    LOGGER = getLogger(
        name="MAIN",
        logger_config={
            "logfile": log_file_path,
            "roll_name": args.roll_name,
        }
    )
    logger.LOGGER = LOGGER
    LOGGER.info(f"日志文件   : {log_file_path}")

    # 应用选项到配置
    if args.debug:
        CONFIG["DEBUG"] = True
    if args.headless:
        CONFIG["HEADLESS"] = True
    if args.mode:
        CONFIG["MODE"] = args.mode
    if args.working_dir:
        resolved = Path(args.working_dir).resolve()
        if not resolved.exists():
            LOGGER.error(f"工作目录不存在: {resolved}")
            sys.exit(1)
        CONFIG["WORKING_DIR"] = str(resolved)

    if args.session_dir:
        temp_session_dir = Path(args.session_dir)
        if temp_session_dir.is_absolute():
            args.session_dir = temp_session_dir.name
        session_dir = (Path("session") / args.session_dir).resolve()  # 相对路径前加 session/ 再解析为绝对路径
        # 确保目录存在
        session_dir.mkdir(parents=True, exist_ok=True)
        CONFIG["SESSION_DIR"] = str(session_dir)
        LOGGER.info(f"会话目录已指定: {CONFIG['SESSION_DIR']}\\main")
    CONFIG["PROMPT_FILE"] = (Path("prompt") / (args.session_dir + ".txt")).resolve()
    if not Path(CONFIG["PROMPT_FILE"]).exists():
        Path(CONFIG["PROMPT_FILE"]).touch()
    if args.test_bat:
        CONFIG["TEST_BAT_PATH"] = str(Path(args.test_bat).resolve())
    if args.max_iterations is not None:
        if args.max_iterations < 1:
            LOGGER.error("--max-iterations 必须是正整数")
            sys.exit(1)
        CONFIG["MAX_ITERATIONS"] = args.max_iterations

    # 初始化所有工具
    if args.ext_tools:
        CONFIG["EXT_TOOLS"] = args.ext_tools
    else:
        CONFIG["EXT_TOOLS"] = []
    from ds.agentTools import init_tools
    init_tools()
    if args.deny_tools:
        from ds.agentTools import TOOLS
        CONFIG["allow_tools"] = [
            tool_name for tool_name in TOOLS.keys()
            if tool_name not in args.deny_tools
        ]
    else:
        from ds.agentTools import TOOLS
        CONFIG["allow_tools"] = [
            tool_name for tool_name in TOOLS.keys()
        ]

    # 确定任务
    task = args.task
    if args.task_path:
        try:
            with open(args.task_path, 'r', encoding='utf-8') as f:
                task = f.read().strip()
        except Exception as e:
            LOGGER.error(f"读取任务文件失败: {e}")
            sys.exit(1)
    if not task and args.rest:
        task = " ".join(args.rest)

    # 打印横幅
    LOGGER.info(f"工作目录 : {CONFIG['WORKING_DIR']}")
    LOGGER.info(f"会话目录 : {CONFIG['SESSION_DIR']}")
    LOGGER.info(f"无头模式   : {CONFIG['HEADLESS']}")
    LOGGER.info(f"调试模式   : {CONFIG['DEBUG']}")
    LOGGER.info(f"最大轮数   : {CONFIG['MAX_ITERATIONS']}")
    LOGGER.info(f"日志文件   : {log_file_path}")
    print()

    # 创建 Agent
    from ds.agent import DeepSeekAgent
    agent = DeepSeekAgent({
        "test_bat": args.test_bat,
        "log_file": log_file_path,
    })

    # 信号处理
    def shutdown(code=0):
        LOGGER.info("正在关闭...")
        try:
            agent.shutdown()
        except:
            pass
        sys.exit(code)

    signal.signal(signal.SIGINT, lambda s, _f: shutdown(0))
    signal.signal(signal.SIGTERM, lambda s, _f: shutdown(0))

    # 无任务则进入交互
    if not args.interactive and not task:
        LOGGER.warn("未提供任务。切换到交互模式...\n")
        args.interactive = True

    try:
        agent.init()
        agent.browser.set_mode(CONFIG["MODE"])
    except Exception as e:
        error_str = traceback.format_exc()
        LOGGER.error(f"任务失败: {e}")
        for error_line in error_str.split("\n"):
            LOGGER.error(error_line)
        sys.exit(1)

    try:
        if args.interactive:
            agent.run_interactive()
        else:
            if args.load_file:
                agent.browser.load_file(args.load_file)
            result = agent.run(task)
            if not result.get("completed", False):
                LOGGER.error("任务失败，未能完成。")
                LOGGER.error(result.get("content", ""))
                shutdown(1)
            if result.get("data", {"content": ""}).get("content", "") == "abort_task":
                shutdown(result.get("data", {"exitcode": 0}).get("exitcode", 0))
    except Exception as e:
        error_str = traceback.format_exc()
        LOGGER.error(f"任务失败: {e}")
        for error_line in error_str.split("\n"):
            LOGGER.error(error_line)
        shutdown(1)

    shutdown(0)


if __name__ == "__main__":
    main()
