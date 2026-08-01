#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# @Time    : 2026/07/31 00:55
# @Author  : Wu_RH
# @FileName: calibrate.py
# src/calibrate.py
#!/usr/bin/env python3
import sys
import time
from playwright.sync_api import sync_playwright
from .config import CONFIG
from .logger import logger

def calibrate():
    print("\n🔬  DeepSeek Agent — Selector Calibration Tool\n")
    print("This tool opens DeepSeek, inspects the DOM, and prints out")
    print("the selectors that your browser.py should use.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=CONFIG["SESSION_DIR"],
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        print("→ Navigating to", CONFIG["DEEPSEEK_URL"], "...")
        page.goto(CONFIG["DEEPSEEK_URL"], wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        print("→ Inspecting DOM...\n")

        report = page.evaluate("""
            () => {
                function isVisible(el) {
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0' && el.offsetParent !== null;
                }
                function classify(el) {
                    return {
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        classes: el.className?.slice?.(0, 120) || null,
                        placeholder: el.placeholder || null,
                        ariaLabel: el.getAttribute('aria-label') || null,
                        dataTestId: el.dataset?.testid || null,
                        role: el.getAttribute('role') || null,
                        visible: isVisible(el),
                        text: (el.innerText || '').slice(0, 40).replace(/\\n/g, ' ') || null,
                        type: el.getAttribute('type') || null,
                    };
                }
                const inputs = Array.from(document.querySelectorAll('textarea, [contenteditable="true"]')).map(classify);
                const buttons = Array.from(document.querySelectorAll('button, [role="button"]'))
                    .filter(isVisible)
                    .map(classify)
                    .slice(0, 30);
                const classFreq = {};
                document.querySelectorAll('*').forEach(el => {
                    (el.getAttribute('class') || '').split(/\\s+/).forEach(c => {
                        if (c.length > 2 && c.length < 50) {
                            classFreq[c] = (classFreq[c] || 0) + 1;
                        }
                    });
                });
                const topClasses = Object.entries(classFreq)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 80)
                    .map(([cls, n]) => ({ cls, n }));
                const suggestedInput = (
                    inputs.find(i => i.placeholder?.toLowerCase().includes('message'))?.id ||
                    inputs.find(i => i.placeholder?.toLowerCase().includes('ask'))?.id ||
                    inputs.find(i => i.visible)?.id ||
                    null
                );
                const sendBtn = buttons.find(b =>
                    /send/i.test(b.ariaLabel || '') ||
                    /send/i.test(b.text || '') ||
                    /send/i.test(b.classes || '')
                );
                const stopBtn = buttons.find(b =>
                    /stop/i.test(b.ariaLabel || '') ||
                    /stop/i.test(b.text || '') ||
                    /stop/i.test(b.classes || '')
                );
                const newChatBtn = buttons.find(b =>
                    /new chat/i.test(b.ariaLabel || '') ||
                    /new chat/i.test(b.text || '') ||
                    /new.?chat/i.test(b.classes || '')
                );
                return {
                    url: window.location.href,
                    title: document.title,
                    inputs,
                    buttons,
                    topClasses,
                    suggestions: { suggestedInput, sendBtn, stopBtn, newChatBtn },
                };
            }
        """)

        sep = '-' * 60
        print(sep)
        print("URL   :", report['url'])
        print("Title :", report['title'])
        print(sep)

        print("\n📥  INPUT ELEMENTS:")
        if not report['inputs']:
            print("  (none found — are you logged in?)")
        for i, el in enumerate(report['inputs']):
            print(f"  [{i}] {el}")

        print("\n🔘  BUTTONS (visible, first 30):")
        for i, el in enumerate(report['buttons']):
            print(f"  [{i}] {el}")

        print("\n🏷️  TOP CSS CLASSES:")
        for item in report['topClasses'][:40]:
            print(f"  {str(item['n']).rjust(4)}x  .{item['cls']}")

        print("\n" + sep)
        print("🎯  SUGGESTED SELECTORS (update browser.py SEL object):")
        print(sep)
        s = report['suggestions']
        if s['suggestedInput']:
            print(f"  chatInput  : '#{s['suggestedInput']}'")
        if s['sendBtn']:
            sel = f"button[aria-label=\"{s['sendBtn']['ariaLabel']}\"]" if s['sendBtn'].get('ariaLabel') else \
                  f"#{s['sendBtn']['id']}" if s['sendBtn'].get('id') else \
                  f".{s['sendBtn']['classes'].split(' ')[0]}"
            print(f"  sendButton : '{sel}'")
        if s['stopBtn']:
            sel = f"button[aria-label=\"{s['stopBtn']['ariaLabel']}\"]" if s['stopBtn'].get('ariaLabel') else \
                  f".{s['stopBtn']['classes'].split(' ')[0]}"
            print(f"  stopButton : '{sel}'")
        if s['newChatBtn']:
            sel = f"button[aria-label=\"{s['newChatBtn']['ariaLabel']}\"]" if s['newChatBtn'].get('ariaLabel') else \
                  f".{s['newChatBtn']['classes'].split(' ')[0]}"
            print(f"  newChat    : '{sel}'")

        print(sep)
        print("\n📸  Taking screenshot → /tmp/deepseek-calibrate.png")
        page.screenshot(path="/tmp/deepseek-calibrate.png", full_page=False)

        print("\n✅  Calibration complete! Update src/browser.py SEL object with the selectors above.")
        print("    Press Ctrl+C to exit.\n")

        try:
            time.sleep(3600)  # 保持浏览器打开
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    calibrate()