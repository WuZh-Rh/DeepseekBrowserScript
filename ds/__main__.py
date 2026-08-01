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
from ds.config import CONFIG
from ds.logger import logger, init_log_file
from ds.agent import DeepSeekAgent

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
    parser.add_argument("-d", "--dir", dest="working_dir", help="设置工作目录（默认当前目录）")
    parser.add_argument("--debug", action="store_true", help="输出详细的调试信息")
    parser.add_argument("--headless", action="store_true", help="无头模式运行浏览器")
    parser.add_argument("--save-log", action="store_true", help="保存会话日志到 ~/.deepseek-agent/logs/")
    parser.add_argument("--calibrate", action="store_true", help="打开浏览器并打印 DOM 信息，帮助修复选择器")
    parser.add_argument("--test-bat", dest="test_bat", help="指定测试脚本（.bat），用于验证最终结果")
    parser.add_argument("--log-path", dest="log_path", help="指定日志目录", default="./logs")
    parser.add_argument("--log-name", dest="log_name", help="指定日志文件名（如 my.log）", default="latest.log")
    parser.add_argument("--no-roll", dest="no_roll", action="store_true", help="禁用日志滚动（追加到同一个文件，默认每次运行生成新文件）")
    parser.add_argument("--roll-name", dest="roll_name", help="滚动日志的时候添加的后缀(YYYY-MM-DD-XXXX-?.log)", default="")
    parser.add_argument("-m", "--max-iterations", type=int, help="限制 Agent 的最大循环轮数（默认 150）")
    parser.add_argument("-S", "--session-dir", dest="session_dir", help="指定会话目录")
    parser.add_argument("--deny-tools", nargs='+', help="禁用指定的工具，空格分隔", default=None)
    parser.add_argument("--task-path", help="从文件读取任务内容")
    parser.add_argument("rest", nargs="*", help="任务文本（不带 -t 时）")
    return parser.parse_args()


def main():
    args = parse_args()

    # 应用选项到配置
    if args.debug:
        CONFIG["DEBUG"] = True
    if args.headless:
        CONFIG["HEADLESS"] = True
    if args.working_dir:
        resolved = Path(args.working_dir).resolve()
        if not resolved.exists():
            logger.error(f"工作目录不存在: {resolved}")
            sys.exit(1)
        CONFIG["WORKING_DIR"] = str(resolved)
    if args.deny_tools:
        from ds.agentTools import TOOLS
        CONFIG["allow_tools"] = [
            tool_name for tool_name in TOOLS.keys()
            if tool_name not in args.deny_tools
        ]
    if args.session_dir:
        session_dir = Path(args.session_dir).resolve()
        # 确保目录存在
        session_dir.mkdir(parents=True, exist_ok=True)
        CONFIG["SESSION_DIR"] = str(session_dir)
        logger.info(f"会话目录已指定: {CONFIG['SESSION_DIR']}")
    if args.test_bat:
        CONFIG["TEST_BAT_PATH"] = str(Path(args.test_bat).resolve())
    if args.max_iterations is not None:
        if args.max_iterations < 1:
            logger.error("--max-iterations 必须是正整数")
            sys.exit(1)
        CONFIG["MAX_ITERATIONS"] = args.max_iterations

    # 初始化日志
    if sys.platform == 'win32':
        if os.path.isabs(args.log_path):
            log_dir = args.log_path
        else:
            log_dir = os.path.join(Path(SELF_PATH), Path(args.log_path))
    else:
        log_dir = os.path.expanduser("~/.deepseek-agent/logs")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = str(log_dir / args.log_name)

    # 如果指定了 log_name，使用固定文件模式（is_fixed=True）
    init_log_file(log_file_path, is_fixed=args.no_roll, roll_name=args.roll_name)
    logger.info(f"日志文件   : {log_file_path}")

    # 确定任务
    task = args.task
    if args.task_path:
        try:
            with open(args.task_path, 'r', encoding='utf-8') as f:
                task = f.read().strip()
        except Exception as e:
            logger.error(f"读取任务文件失败: {e}")
            sys.exit(1)
    if not task and args.rest:
        task = " ".join(args.rest)

    # 打印横幅
    logger.banner()
    logger.info(f"工作目录 : {CONFIG['WORKING_DIR']}")
    logger.info(f"会话目录 : {CONFIG['SESSION_DIR']}")
    logger.info(f"无头模式   : {CONFIG['HEADLESS']}")
    logger.info(f"调试模式   : {CONFIG['DEBUG']}")
    logger.info(f"最大轮数   : {CONFIG['MAX_ITERATIONS']}")
    logger.info(f"日志文件   : {log_file_path}")
    print()

    # 创建 Agent
    agent = DeepSeekAgent({
        "save_log": args.save_log,
        "test_bat": args.test_bat,
        "log_file": log_file_path,
    })

    # 信号处理
    def shutdown(code=0):
        logger.info("正在关闭...")
        try:
            agent.shutdown()
        except:
            pass
        sys.exit(code)

    signal.signal(signal.SIGINT, lambda s, f: shutdown(0))
    signal.signal(signal.SIGTERM, lambda s, f: shutdown(0))

    # 校准模式
    if args.calibrate:
        logger.header("校准模式 — 读取 DOM 选择器")
        agent.init()
        agent.browser.dump_debug_info()
        agent.browser.screenshot()
        logger.info("完成。如需更新选择器，请查看上面的输出。")
        shutdown(0)

    # 无任务则进入交互
    if not args.interactive and not task:
        logger.warn("未提供任务。切换到交互模式...\n")
        args.interactive = True

    try:
        agent.init()
    except Exception as e:
        error_str = traceback.format_exc()
        logger.error(f"任务失败: {e}")
        for error_line in error_str.split("\n"):
            logger.error(error_line)
        sys.exit(1)

    try:
        if args.interactive:
            agent.run_interactive()
        else:
            result = agent.run(task)
            if not result.get("completed", False):
                logger.error("任务失败，未能完成。")
                logger.error(result.get("content", ""))
                shutdown(1)
    except Exception as e:
        error_str = traceback.format_exc()
        logger.error(f"任务失败: {e}")
        for error_line in error_str.split("\n"):
            logger.error(error_line)
        shutdown(1)

    shutdown(0)


if __name__ == "__main__":
    main()
