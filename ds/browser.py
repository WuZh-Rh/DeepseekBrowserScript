#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:32
# @Author  : Wu_RH
# @FileName: browser.py
# src/browser.py
import json
import time
import traceback

from playwright.sync_api import sync_playwright
from pathlib import Path
from .config import CONFIG
from .logger import LOGGER
from .prompt import ConversationManager


class DeepSeekBrowser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._closed = False

    def launch(self):
        LOGGER.info("正在启动浏览器，使用持久化会话...")
        self.playwright = sync_playwright().start()
        session_dir = Path(CONFIG["SESSION_DIR"]) / "main"
        session_dir.mkdir(parents=True, exist_ok=True)

        # 持久化上下文
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=CONFIG["HEADLESS"],
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 "
                       "Safari/537.36",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )
        # 获取或创建页面
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        # 注入脚本隐藏自动化特征
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        self._navigate(CONFIG["DEEPSEEK_URL"])
        self._ensure_logged_in()
        LOGGER.success("浏览器已就绪！")

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except:
            pass

    def _navigate(self, url):
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)
        except Exception as e:
            LOGGER.warn(f"导航警告: {e}")

    def new_chat(self):
        # 尝试点击“新对话”按钮
        new_chat_selectors = [
            'button[aria-label*="New chat" i]',
            'button[aria-label*="New conversation" i]',
            'a[href="/"][aria-label]',
            '[data-testid="new-chat"]',
            '[class*="new-chat"]',
            '[class*="newChat"]',
        ]
        for sel in new_chat_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(1)
                    LOGGER.dim("已启动新对话")
                    return
            except:
                pass
        # 后备：导航到首页
        self._navigate(CONFIG["DEEPSEEK_URL"])
        LOGGER.dim("已导航到 DeepSeek 首页（新对话）")

    def _ensure_logged_in(self):
        time.sleep(2)
        # 检查是否需要登录
        needs_login = self.page.evaluate("""
            () => {
                const url = window.location.href;
                return url.includes('/auth') || url.includes('/login') || url.includes('/sign') ||
                       !!document.querySelector('input[type="password"]');
            }
        """)
        if needs_login:
            self._print_login_banner()
            self._wait_for_enter()
            time.sleep(2)

    def _print_login_banner(self):
        print()
        LOGGER.warn("=" * 52)
        LOGGER.warn("🔐  需要登录")
        LOGGER.warn("")
        LOGGER.warn("1. 在浏览器窗口中登录 DeepSeek")
        LOGGER.warn("2. 返回此处并按下  ENTER  继续")
        LOGGER.warn("=" * 52)
        print()

    def _wait_for_enter(self):
        input("按 Enter 继续...")

    def send_message(self, text):
        # 查找输入框
        el, is_textarea = self._find_input()
        el.click(force=True)
        time.sleep(0.2)
        # 清空
        self.page.keyboard.press("Control+a")
        time.sleep(0.1)
        if is_textarea:
            el.fill(text)
        else:
            # contenteditable
            self.page.evaluate("""
                (element, content) => {
                    element.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('delete', false, null);
                    document.execCommand('insertText', false, content);
                    element.dispatchEvent(new InputEvent('input', { bubbles: true, data: content }));
                }
            """, el, text)
        time.sleep(CONFIG["SEND_DELAY"] / 1000.0)
        clicked = self._click_send_button()
        if not clicked:
            self.page.keyboard.press("Enter")
        time.sleep(0.5)

    def _find_input(self):
        chat_input_selectors = [
            '#chat-input',
            'textarea[placeholder]',
            'textarea',
            '[contenteditable="true"][role="textbox"]',
            '[contenteditable="true"]',
        ]
        for sel in chat_input_selectors:
            try:
                el = self.page.wait_for_selector(sel, timeout=4000, state="visible")
                if el:
                    tag = el.evaluate("e => e.tagName.toLowerCase()")
                    is_editable = el.evaluate("e => e.isContentEditable")
                    is_textarea = tag == 'textarea' and not is_editable
                    return el, is_textarea
            except:
                continue
        raise RuntimeError(
            "找不到 DeepSeek 的聊天输入框。\n"
            "  → 请确保页面已完全加载并且你已经登录。\n"
            "  → 使用 --debug 参数运行以检查 DOM。\n"
            "  → 运行: python src/calibrate.py 自动探测选择器。"
        )

    def _click_send_button(self):
        send_selectors = [
            'button[aria-label*="Send" i]',
            'button[aria-label*="send" i]',
            '[data-testid="send-button"]',
            'button[type="submit"]',
            '[class*="send-btn"]',
            '[class*="sendBtn"]',
            '[class*="send-button"]',
        ]
        for sel in send_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible() and el.is_enabled():
                    el.click()
                    return True
            except:
                pass
        return False

    def wait_for_response(self, conversation: ConversationManager):
        def click_retry():
            return self.page.evaluate("""
                () => {
                    const xpath = "//*[contains(text(), '消息发送过于频繁')]";
                    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    const node = result.singleNodeValue;
                    if (!node) return false;
                    // 查找错误文本前面的第一个 div[role="button"]（即你指定的这个按钮）
                    const btnXPath = ".//preceding::div[@role='button'][1]";
                    const btnResult = document.evaluate(btnXPath, node, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    const btn = btnResult.singleNodeValue;
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    return false;
                }
            """)
        timeout = CONFIG["RESPONSE_TIMEOUT"] / 1000.0
        stable_delay = CONFIG["STABLE_DELAY"] / 1000.0
        start = time.time()
        # 阶段1：等待新消息出现
        initial_count = self._get_message_count()
        appeared = False
        while time.time() - start < 12:
            prompts = self._get_prompt_texts()
            if any("达到对话长度上限" in prompt for prompt in prompts):
                raise RuntimeError("对话达到长度限制")
            retry_count = -1
            retry_fail = 0
            for retry_count in range(99, -1, -1):
                if not any("消息发送过于频繁" in prompt for prompt in prompts):
                    break
                LOGGER.warn(f"消息发送过于频繁 正在进行第{100-retry_count}/100次重试")
                click = click_retry()
                if not click:
                    retry_fail += 1
                    LOGGER.warn(f"重试按钮点击失败({retry_fail}/10)")
                time.sleep(3)
                if retry_fail == 10:
                    raise RuntimeError("消息发送过于频繁且重试按钮点击失败")
                prompts = self._get_prompt_texts()
                start = time.time()
                initial_count = self._get_message_count()
            if retry_count == 0:
                raise RuntimeError("消息发送过于频繁")
            if self._get_message_count() > initial_count:
                appeared = True
                break
            time.sleep(0.4)
        if not appeared:
            LOGGER.warn("响应可能延迟 — 继续等待...")

        # 阶段2：等待文本稳定
        last_text = ""
        stable_start = None
        while time.time() - start < timeout:
            text = self._extract_last_message()
            if text in [i["content"] for i in conversation.messages]:
                continue
            if text != last_text:
                last_text = text
                stable_start = None
            elif text:
                if stable_start is None:
                    stable_start = time.time()
                elif time.time() - stable_start >= stable_delay:
                    if not self._is_generating():
                        break
                    stable_start = None
            # 进度
            dot = '.' * (int(time.time()) % 4)
            LOGGER.thinking(f"正在接收响应{dot}  ({len(text)} 字符)")
            time.sleep(0.5)

        LOGGER.clear_line()
        final = self._extract_last_message()
        return final

    def _get_message_count(self):
        return self.page.evaluate("""
            () => {
                const candidates = [
                    '[class*="assistant"][class*="message"]',
                    '[data-role="assistant"]',
                    '[class*="markdown-content"]',
                    '.ds-markdown',
                    '[class*="chat-message"]',
                    '[class*="message-bubble"]',
                ];
                for (const sel of candidates) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) return els.length;
                }
                return document.querySelectorAll('[class*="message"]').length;
            }
        """)

    def _extract_last_message(self):
        return self.page.evaluate("""
            () => {
                const thinks = document.querySelectorAll('.ds-think-content');
                if (!thinks.length) return '';
                const thinkEl = thinks[thinks.length - 1];
                const msgEl = thinkEl.closest('.ds-message, [data-role="assistant"]');
                if (!msgEl) return thinkEl.textContent.trim();
                const thinking = thinkEl.textContent.trim();
                const clone = msgEl.cloneNode(true);
                const ct = clone.querySelector('.ds-think-content');
                if (ct) ct.remove();
                const answer = clone.textContent.trim();
                if (thinking && answer) {
                    return '【思考】\\n' + thinking + '\\n\\n【输出】\\n' + answer;
                } else if (thinking) {
                    return thinking;
                } else {
                    return answer;
                }
            }
        """)

    def _is_generating(self):
        return self.page.evaluate("""
            () => {
                // ===== 1. 优先检测：是否存在“禁用的发送键”（即生成已结束） =====
                // 查找所有带有 ds-button 类的按钮
                const buttons = document.querySelectorAll('div[role="button"].ds-button');
                for (const btn of buttons) {
                    // 检查是否为发送图标（向上箭头）—— 通过 SVG path 特征判断
                    const svg = btn.querySelector('svg');
                    if (!svg) continue;
                    const path = svg.querySelector('path');
                    if (!path) continue;
                    const d = path.getAttribute('d');
                    // 发送键的特征：path 包含 "M8.3125" 且不包含 "M2"（矩形标识）
                    if (d && d.includes('M8.3125') && !d.includes('M2')) {
                        // 如果是禁用的发送键，则生成已结束，返回 false
                        if (btn.classList.contains('ds-button--disabled')) {
                            return false;
                        }
                        // 如果找到可用的发送键（非禁用），虽然不太可能出现在生成中，但为了安全也视为结束
                        // 但这里我们不处理，因为生成中应该是停止键而非发送键
                    }
                }

                // ===== 2. 原逻辑：停止按钮检测 =====
                const stopSelectors = [
                    'button[aria-label*="Stop" i]',
                    '[class*="stop-gen"]',
                    '[class*="stopGen"]',
                    '[class*="generating"]',
                ];
                for (const sel of stopSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const s = window.getComputedStyle(el);
                        if (s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0') return true;
                    }
                }
                const loaderSelectors = [
                    '[class*="typing"]',
                    '[class*="loading"]',
                    '[class*="spinner"]',
                    '[class*="blink"]',
                    '[class*="cursor"]',
                    '[class*="pulsing"]',
                    'svg[class*="loading"]',
                    'svg[class*="spinner"]',
                ];
                for (const sel of loaderSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const s = window.getComputedStyle(el);
                        if (s.display !== 'none' && s.visibility !== 'hidden') return true;
                    }
                }
                return false;
            }
        """)

    def _get_prompt_texts(self):
        """
        从页面上提取所有可能的提示框文本（如“达到对话长度上限，请开启新对话”）。
        基于稳定的 .ds-flex 类定位，排除助手消息内部的按钮组。
        返回所有匹配文本的列表。
        """
        try:
            texts = self.page.evaluate("""
                () => {
                    const results = [];

                    document.querySelectorAll('.ds-flex').forEach(flex => {
                        const parent = flex.parentElement;
                        if (!parent) return;

                        // 跳过位于 .ds-message 内部的按钮（助手消息中的操作按钮）
                        if (parent.closest && parent.closest('.ds-message')) {
                            return;
                        }

                        const siblings = [parent.previousElementSibling, parent.nextElementSibling];
                        for (const sib of siblings) {
                            if (!sib) continue;
                            const span = sib.querySelector('span');
                            if (span) {
                                const text = span.textContent.trim();
                                if (text.length > 0) {
                                    results.push(text);
                                }
                            }
                        }

                        const spanInParent = parent.querySelector('span');
                        if (spanInParent) {
                            const text = spanInParent.textContent.trim();
                            if (text.length > 0) {
                                results.push(text);
                            }
                        }
                    });

                    // 如果没找到，再试一个更宽松的 fallback（只用于调试）
                    if (results.length === 0) {
                        const fallback = document.querySelector('span:has-text("开启新对话")');
                        if (fallback) {
                            const text = fallback.textContent.trim();
                            if (text.length > 0) results.push(text);
                        }
                    }

                    return results;  // 返回数组
                }
            """)
            return texts if texts else []
        except Exception:
            return []

    def open_sidebar(self):
        """确保侧边栏展开。如果侧边栏已打开则忽略，否则点击汉堡菜单按钮。"""
        # 先检查侧边栏是否已可见（通过历史列表容器是否存在且可见）
        sidebar_visible = self.page.evaluate("""
() => {
    const container = document.querySelector('[class*="sidebar"], [class*="history"], [class*="conversation-list"]');
    if (!container) return false;
    const rect = container.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}
        """)
        if sidebar_visible:
            return

        # 尝试点击汉堡菜单按钮（通常在左上角）
        menu_selectors = [
            'button[aria-label*="menu" i]',
            'button[aria-label*="sidebar" i]',
            'button[aria-label*="history" i]',
            '[class*="menu-btn"]',
            '[class*="hamburger"]',
            '[class*="sidebar-toggle"]',
            'button:has(svg path[d*="M3 6h10M3 10h10M3 14h10"])',  # 三条横线图标
        ]
        for sel in menu_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible() and btn.is_enabled():
                    btn.click()
                    time.sleep(0.5)
                    return
            except:
                pass
        # LOGGER.warn("未找到侧边栏切换按钮，可能已经展开或页面结构变化")

    def list_chats(self):
        """获取侧边栏中所有对话的标题列表（按显示顺序）"""
        self.open_sidebar()
        # 等待列表加载
        self.page.wait_for_selector('[class*="c08e6e93"]', timeout=5000, state="attached")
        titles = self.page.evaluate("""
            () => {
                // 根据你提供的 HTML，标题在 div.c08e6e93 中
                const items = document.querySelectorAll('[class*="c08e6e93"]');
                return Array.from(items).map(el => el.textContent.trim()).filter(t => t.length > 0);
            }
        """)
        return titles

    def select_chat_by_title(self, title, partial_match=True):
        """
        根据标题选择对话。
        :param title: 要匹配的标题
        :param partial_match: 是否进行部分匹配（默认 True）
        """
        self.open_sidebar()
        # 找到包含标题的 a 标签（整个条目可点击）
        if partial_match:
            selector = f'a:has(div[class*="c08e6e93"]:has-text("{title}"))'
        else:
            selector = f'a:has(div[class*="c08e6e93"]:text-is("{title}"))'
        try:
            link = self.page.wait_for_selector(selector, timeout=3000, state="visible")
            link.click()
            time.sleep(1.5)  # 等待页面切换
            LOGGER.info(f"已切换到对话：{title}")
        except Exception:
            # 降级方案：遍历所有条目，用 javascript 匹配
            clicked = self.page.evaluate("""
                (targetTitle, partial) => {
                    const items = document.querySelectorAll('a[href*="/a/chat/s/"]');
                    for (const a of items) {
                        const div = a.querySelector('[class*="c08e6e93"]');
                        if (!div) continue;
                        const text = div.textContent.trim();
                        if (partial ? text.includes(targetTitle) : text === targetTitle) {
                            a.click();
                            return true;
                        }
                    }
                    return false;
                }
            """, title, partial_match)
            if not clicked:
                raise RuntimeError(f"未找到标题为 '{title}' 的对话")

    def select_chat_by_index(self, index):
        """
        根据索引选择对话（0 为第一条）。
        """
        self.open_sidebar()
        # 获取所有对话条目（a 标签）
        links = self.page.query_selector_all('a[href*="/a/chat/s/"]')
        if index >= len(links):
            raise IndexError(f"索引 {index} 超出范围，共有 {len(links)} 个对话")
        link = links[index]
        # 确保可见
        link.scroll_into_view_if_needed()
        link.click()
        time.sleep(1.5)
        LOGGER.info(f"已选择索引 {index} 的对话")

    def get_current_chat_title(self):
        """获取当前正在查看的对话标题（从页面顶部或 URL 推断）"""
        # 尝试从页面顶部的标题元素获取
        title_sel = '[class*="chat-title"], [class*="conversation-title"], header [class*="title"]'
        try:
            el = self.page.query_selector(title_sel)
            if el:
                return el.text_content().strip()
        except:
            pass
        # 降级：从 URL 中提取 chat id，然后从侧边栏匹配
        url = self.page.url
        import re
        match = re.search(r'/a/chat/s/([a-f0-9-]+)', url)
        if match:
            chat_id = match.group(1)
            # 在侧边栏中查找对应的标题
            title = self.page.evaluate("""
                (cid) => {
                    const items = document.querySelectorAll('a[href*="/a/chat/s/"]');
                    for (const a of items) {
                        if (a.href.includes(cid)) {
                            const div = a.querySelector('[class*="c08e6e93"]');
                            return div ? div.textContent.trim() : null;
                        }
                    }
                    return null;
                }
            """, chat_id)
            return title
        return None

    # ----- 获取工具调用记录（纯 Python 解析） -----
    def get_tool_calls_history(self):
        """
        从页面中所有助手消息的 DOM 中提取工具调用 JSON。
        返回扁平列表，每个元素为 {'name': str, 'args': dict}。
        """
        all_tools = []
        try:
            selector = '.ds-assistant-message-main-content'
            elements = self.page.query_selector_all(selector)
            for el in elements:
                pre = el.query_selector('.md-code-block pre')
                if not pre:
                    continue
                json_text = pre.inner_text().strip()
                try:
                    data = json.loads(json_text)
                except json.JSONDecodeError:
                    continue  # 跳过非 JSON 块

                tools = []
                if isinstance(data, list):
                    for item in data:
                        if 'name' in item and isinstance(item['name'], str):
                            tools.append({'name': item['name'], 'args': item.get('args', {})})
                elif isinstance(data, dict):
                    if 'tools' in data and isinstance(data['tools'], list):
                        for item in data['tools']:
                            if 'name' in item and isinstance(item['name'], str):
                                tools.append({'name': item['name'], 'args': item.get('args', {})})
                    else:
                        name = data.get('name')
                        if name and isinstance(name, str):
                            tools.append({'name': name, 'args': data.get('args', {})})
                all_tools.append(tools)
        except Exception:
            pass
        return all_tools

    def get_latest_tool_calls(self):
        """
        从最后一条助手消息 DOM 提取工具调用。
        返回统一结构：
            {"type": "tool_calls", "tools": [...]}
            {"type": "final", "content": "文本内容"}
            {"type": "error", "message": "错误信息"}
        """
        try:
            selector = '.ds-assistant-message-main-content'
            elements = self.page.query_selector_all(selector)
            if not elements:
                return {"type": "final", "content": ""}

            last_el = elements[-1]
            # 先拿完整文本（给 final 用）
            full_text = last_el.inner_text().strip()

            # 尝试拿工具调用
            pre = last_el.query_selector('.md-code-block pre')
            if not pre:
                return {"type": "final", "content": full_text}

            json_text = pre.inner_text().strip()
            data = json.loads(json_text)

            tools = []
            if isinstance(data, list):
                for item in data:
                    if 'name' in item:
                        tools.append({'name': item['name'], 'args': item.get('args', {})})
            elif isinstance(data, dict):
                if 'tools' in data:
                    for item in data['tools']:
                        if 'name' in item:
                            tools.append({'name': item['name'], 'args': item.get('args', {})})
                else:
                    name = data.get('name')
                    if name:
                        tools.append({'name': name, 'args': data.get('args', {})})

            if tools:
                return {"type": "tool_call", "tools": tools}
            else:
                return {"type": "final", "content": full_text}

        except json.JSONDecodeError:
            return {"type": "error", "message": f"调用工具失败[JSON解析失败]: " + traceback.format_exc()}
        except Exception:
            return {"type": "error", "message": f"提取工具调用失败: " + traceback.format_exc()}

    def load_file(self, file_paths, selector=None):
        """
        模拟通过文件输入框上传文件（相当于点击“选择文件”对话框）。
        不依赖操作系统拖拽API，仅通过Web的 <input type="file"> 元素实现。

        :param file_paths: 文件路径，可以是字符串（单个）或列表（多个）
        :param selector: 可选，指定文件输入框的CSS选择器。
                         如果不提供，将自动尝试常见的选择器。
        :raises RuntimeError: 如果找不到文件输入元素
        """
        # 统一转换为字符串列表
        if isinstance(file_paths, (str, Path)):
            file_paths = [str(file_paths)]
        else:
            file_paths = [str(p) for p in file_paths]

        # 定位文件输入框
        if selector is None:
            # 常见选择器清单
            candidates = [
                'input[type="file"]',
                '[class*="file-input"]',
                '[class*="upload"]',
                '[data-testid="file-upload"]',
                '[role="button"][aria-label*="upload" i] + input[type="file"]',  # 有些按钮后面跟隐藏input
            ]
            found_sel = None
            for sel in candidates:
                try:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        found_sel = sel
                        break
                except:
                    pass
            if found_sel is None:
                # 尝试查找所有隐藏的file input（很多场景下它是display:none）
                all_inputs = self.page.query_selector_all('input[type="file"]')
                if all_inputs:
                    found_sel = 'input[type="file"]'
                else:
                    raise RuntimeError(
                        "未找到文件上传输入框，请手动提供 selector 参数。"
                        "你可以使用浏览器开发者工具找到对应的 input[type='file'] 选择器。"
                    )
            selector = found_sel

        # 设置文件（Playwright会自动触发 change 事件）
        self.page.set_input_files(selector, file_paths)
        LOGGER.info(f"已上传文件: {', '.join(file_paths)}")
        # 可选的延迟，让页面处理上传
        time.sleep(0.5)
