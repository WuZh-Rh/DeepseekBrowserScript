#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:32
# @Author  : Wu_RH
# @FileName: browser.py
# src/browser.py
import time
import sys
from playwright.sync_api import sync_playwright
from pathlib import Path
from .config import config
from .logger import logger


class DeepSeekBrowser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._closed = False

    def launch(self):
        logger.info("正在启动浏览器，使用持久化会话...")
        self.playwright = sync_playwright().start()
        session_dir = Path(config["SESSION_DIR"])
        session_dir.mkdir(parents=True, exist_ok=True)

        # 持久化上下文
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=config["HEADLESS"],
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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

        self._navigate(config["DEEPSEEK_URL"])
        self._ensure_logged_in()
        logger.success("浏览器已就绪！")

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
            logger.warn(f"导航警告: {e}")

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
                    logger.dim("已启动新对话")
                    return
            except:
                pass
        # 后备：导航到首页
        self._navigate(config["DEEPSEEK_URL"])
        logger.dim("已导航到 DeepSeek 首页（新对话）")

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
        logger.warn("=" * 52)
        logger.warn("🔐  需要登录")
        logger.warn("")
        logger.warn("1. 在浏览器窗口中登录 DeepSeek")
        logger.warn("2. 返回此处并按下  ENTER  继续")
        logger.warn("=" * 52)
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
        time.sleep(config["SEND_DELAY"] / 1000.0)
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

    def wait_for_response(self):
        timeout = config["RESPONSE_TIMEOUT"] / 1000.0
        stable_delay = config["STABLE_DELAY"] / 1000.0
        start = time.time()
        # 阶段1：等待新消息出现
        initial_count = self._get_message_count()
        appeared = False
        while time.time() - start < 12:
            if self._get_message_count() > initial_count:
                appeared = True
                break
            time.sleep(0.4)
        if not appeared:
            logger.warn("响应可能延迟 — 继续等待...")

        # 阶段2：等待文本稳定
        last_text = ""
        stable_start = None
        while time.time() - start < timeout:
            text = self._extract_last_message()
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
            dot = '.' * ((int(time.time()) % 4))
            logger.thinking(f"正在接收响应{dot}  ({len(text)} 字符)")
            time.sleep(0.5)

        logger.clear_line()
        final = self._extract_last_message()
        return self._clean_text(final)

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
                function getFullText(el) {
                    if (!el) return '';
                    let result = '';
                    function walk(node) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            result += node.textContent;
                            return;
                        }
                        if (node.nodeType !== Node.ELEMENT_NODE) return;
                        const tag = node.tagName.toLowerCase();
                        if (tag === 'pre') {
                            const codeEl = node.querySelector('code');
                            if (codeEl) {
                                const cls = codeEl.className || '';
                                const lang = (cls.match(/language-(\\S+)/) || [])[1] || '';
                                const body = codeEl.textContent || '';
                                result += '\\n```' + lang + '\\n' + body + '\\n```\\n';
                            } else {
                                result += '\\n```\\n' + node.textContent + '\\n```\\n';
                            }
                            return;
                        }
                        if (tag === 'code') {
                            const parentTag = node.parentElement?.tagName?.toLowerCase() || '';
                            if (parentTag !== 'pre') {
                                result += '`' + node.textContent + '`';
                            }
                            return;
                        }
                        for (const child of node.childNodes) walk(child);
                        if (['p','div','li','br','h1','h2','h3','h4','h5','h6'].includes(tag)) {
                            result += '\\n';
                        }
                    }
                    walk(el);
                    return result.trim();
                }
                function isAssistant(el) {
                    const cls = el.className || '';
                    if (cls.includes('ds-assistant-message-main-content')) return true;
                    if (el.getAttribute('data-role') === 'assistant') return true;
                    if (cls.includes('assistant') && !cls.includes('user')) return true;
                    return false;
                }
                function isUserContent(text) {
                    return text.includes('[工具结果结束]');
                }
                // 优先精确选择器
                const primary = ['.ds-assistant-message-main-content', '[data-role="assistant"]'];
                for (const sel of primary) {
                    const els = document.querySelectorAll(sel);
                    if (els.length) {
                        const el = els[els.length - 1];
                        const text = el.innerText || '';
                        if (isAssistant(el) && !isUserContent(text) && text.length > 5) {
                            return getFullText(el);
                        }
                    }
                }
                // 后备
                const allBlocks = document.querySelectorAll('[class*="message"]');
                const candidates = [];
                for (const el of allBlocks) {
                    const text = el.innerText || '';
                    if (isAssistant(el) && !isUserContent(text) && text.length > 10) {
                        candidates.push(el);
                    }
                }
                if (candidates.length) {
                    return getFullText(candidates[candidates.length - 1]);
                }
                return '';
            }
        """)

    def _is_generating(self):
        return self.page.evaluate("""
            () => {
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

    def _clean_text(self, text):
        if not text:
            return ""
        import re
        # 移除思考块
        text = re.sub(r'<think>[\s\S]*?</think>\n?', '', text, flags=re.I)
        # 移除 Thinking 头部
        text = re.sub(r'^Thinking\.{0,3}\n[\s\S]*?\n\n', '', text, flags=re.M)
        # 移除复制按钮残留
        text = re.sub(r'^\d+(?:Copy|Run|Insert|Edit)\b.*$', '', text, flags=re.M)
        # 压缩空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    # 调试和校准
    def dump_debug_info(self):
        info = self.page.evaluate("""
            () => {
                const classFreq = {};
                document.querySelectorAll('*').forEach(el => {
                    el.classList.forEach(c => {
                        if (c.match(/message|chat|input|send|stop|markdown|content|assistant|user|bot/i)) {
                            classFreq[c] = (classFreq[c] || 0) + 1;
                        }
                    });
                });
                const inputs = Array.from(document.querySelectorAll('textarea, [contenteditable]')).map(e => ({
                    tag: e.tagName,
                    id: e.id || null,
                    class: e.className?.slice(0, 80) || null,
                    placeholder: e.placeholder || null,
                    editable: e.isContentEditable,
                    visible: e.offsetParent !== null,
                }));
                return {
                    url: window.location.href,
                    title: document.title,
                    classes: Object.entries(classFreq).sort((a,b) => b[1]-a[1]).slice(0,40),
                    inputs: inputs,
                };
            }
        """)
        print('\n' + '═'*60)
        print("  DOM 调试信息")
        print('═'*60)
        print(f"URL   : {info['url']}")
        print(f"标题 : {info['title']}")
        print("\n输入元素:")
        for i in info['inputs']:
            print(" ", i)
        print("\n匹配的 CSS 类（按频率）:")
        for cls, count in info['classes']:
            print(f"  {str(count).rjust(3)}x  .{cls}")
        print('═'*60 + '\n')

    def screenshot(self, file_path="/tmp/deepseek-agent-debug.png"):
        self.page.screenshot(path=file_path, full_page=False)
        logger.info(f"截屏已保存: {file_path}")