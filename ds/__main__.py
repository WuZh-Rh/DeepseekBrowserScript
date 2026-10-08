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
    argv = sys.argv[1:]

    # 只有当第一个位置参数是 resume/continue/r 时，才启用 argparse 子命令；
    # 否则裸任务文本（如 ds "写个脚本"）会与子命令冲突。
    _VALUE_OPTS = {"-t", "--task", "-d", "--dir", "--work-dir", "--test-bat",
                   "--log-path", "--roll-name", "-m", "--max-iterations",
                   "-S", "--session-dir", "--task-path", "--load-file"}

    def first_positional(tokens):
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t == "--":
                return tokens[i + 1] if i + 1 < len(tokens) else None
            if t.startswith("-") and t != "-":
                if "=" in t:
                    i += 1
                elif t in _VALUE_OPTS:
                    i += 2
                else:
                    i += 1
            else:
                return t
        return None

    fp = first_positional(argv)
    use_sub = fp is not None and fp.lower() in ("resume", "continue", "r")

    # 全局参数定义。主 parser 用正常默认值；子 parser 用 SUPPRESS 默认值，
    # 这样当参数出现在子命令之前时，主 parser 的结果不会被子 parser 覆盖。
    def _add_common(p, suppress):
        def d(v):
            return argparse.SUPPRESS if suppress else v
        p.add_argument("-t", "--task", default=d(None), help="要运行的任务")
        p.add_argument("-i", "--interactive", action="store_true", default=d(False),
                       help="交互式 REPL 模式")
        p.add_argument("-d", "--dir", "--work-dir", dest="working_dir", default=d(None),
                       help="设置工作目录")
        p.add_argument("--debug", action="store_true", default=d(False), help="输出详细的调试信息")
        p.add_argument("--headless", action="store_true", default=d(False), help="无头模式运行浏览器")
        p.add_argument("--test-bat", dest="test_bat", default=d(None), help="指定测试脚本")
        p.add_argument("--log-path", dest="log_path", default=d("./logs"), help="指定日志目录")
        p.add_argument("--roll-name", dest="roll_name", default=d(""), help="日志滚动后缀")
        p.add_argument("-m", "--max-iterations", type=int, default=d(None),
                       help="Agent 最大循环轮数")
        p.add_argument("-S", "--session-dir", dest="session_dir", default=d("main"),
                       help="指定会话目录")
        p.add_argument("--deny-tools", nargs='+', default=d(None), help="禁用指定的工具")
        p.add_argument("--ext-tools", nargs='+', default=d(None), help="扩展工具")
        p.add_argument("--mode", choices=["fast", "expert", "vision"], default=d("fast"),
                       help="DeepSeek 模式")
        p.add_argument("--task-path", default=d(None), help="从文件读取任务内容")
        p.add_argument("--load-file", default=d(None), help="上传/加载指定文件")

    main_common = argparse.ArgumentParser(add_help=False)
    _add_common(main_common, suppress=False)
    sub_common = argparse.ArgumentParser(add_help=False)
    _add_common(sub_common, suppress=True)

    parser = argparse.ArgumentParser(
        description="DeepSeek 浏览器代理 — 通过浏览器自动化实现的 AI 编码代理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[main_common],
        epilog="""
示例:
  python -m ds "写一个 Hello World"
  python -m ds --interactive
  python -m ds -S test "构建项目"

子命令:
  python -m ds resume                 # 衔接最近一次对话，读页面最后一条消息继续
  python -m ds resume -I 1            # 衔接侧边栏索引为 1 的对话，继续
  python -m ds resume -T 爬虫          # 衔接标题含“爬虫”的对话，继续
  python -m ds resume "新任务"         # 衔接最近一次对话，并发起新任务

注意：全局参数（-S/-d/-m/--mode 等）在子命令前后都可以用。
        """,
    )

    if use_sub:
        subparsers = parser.add_subparsers(dest="command", metavar="{resume}")
        p_resume = subparsers.add_parser(
            "resume", aliases=["continue", "r"], parents=[sub_common],
            help="衔接历史对话（不新建）。省略任务时直接读页面最后一条消息继续。",
        )
        p_resume.add_argument("-I", "--index", dest="resume_index", type=int, default=None,
                              help="侧边栏索引（0 为最近一次）")
        p_resume.add_argument("-T", "--title", dest="resume_title", default=None,
                              help="标题片段（匹配侧边栏对话标题）")
        p_resume.add_argument("resume_task", nargs="*", default=[],
                              help="衔接后要发送的任务；省略则直接读页面最后一条消息继续")
        args = parser.parse_args()
        if args.resume_index is not None and args.resume_title is not None:
            parser.error("resume: --index 与 --title 不能同时使用")
        if args.resume_index is not None:
            if args.resume_index < 0:
                parser.error("resume: --index 不能为负数")
            args.resume = str(args.resume_index)
        elif args.resume_title is not None:
            args.resume = args.resume_title
        else:
            args.resume = "__latest__"
        args.rest = list(args.resume_task)
    else:
        parser.add_argument("rest", nargs="*", help="任务文本")
        args = parser.parse_args()
        args.resume = None
        args.rest = list(args.rest)

    return args


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
    if type(task) is list:
        task = " ".join(args.task)

    # 打印横幅
    if args.resume is not None:
        LOGGER.info(f"衔接对话 : {args.resume}（将切换到历史会话而非新建）")
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
        "resume": args.resume,
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

    # 无任务时的处理
    resume_no_task = False
    if not args.interactive and not task:
        if args.resume is not None:
            # resume 且未附带任务：不发送任何消息，直接读页面最后一条消息继续
            resume_no_task = True
            LOGGER.info("resume 未附带任务：将从页面最后一条消息继续（不发送新消息）")
        else:
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
            result = agent.run(task, no_send=resume_no_task)
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
