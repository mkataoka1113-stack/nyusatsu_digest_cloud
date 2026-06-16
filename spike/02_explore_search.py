# -*- coding: utf-8 -*-
"""
'調達情報検索'ページを開き、検索条件フォーム（業種・工事種別など）の構造を調べる。
読み取り専用。検索ボタンはまだ押さない。
"""
import sys
from playwright.sync_api import sync_playwright

URL = "https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115"

sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    page = browser.new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    print("=== ページタイトル ===")
    print(page.title())
    print("=== URL ===")
    print(page.url)

    print("\n=== input/select/textarea 要素 ===")
    for el in page.locator("input, select, textarea").all():
        tag = el.evaluate("e => e.tagName")
        name = el.get_attribute("name")
        eid = el.get_attribute("id")
        etype = el.get_attribute("type")
        value = el.get_attribute("value")
        print(f"- tag={tag} type={etype} name={name} id={eid} value={value}")

    print("\n=== ボタン類 ===")
    for el in page.locator("button, input[type=submit], input[type=button]").all():
        text = (el.text_content() or "").strip()
        name = el.get_attribute("name")
        value = el.get_attribute("value")
        print(f"- text='{text}' name={name} value={value}")

    print("\n操作確認のため20秒間ブラウザを開いたままにします...")
    page.wait_for_timeout(20000)
    browser.close()
