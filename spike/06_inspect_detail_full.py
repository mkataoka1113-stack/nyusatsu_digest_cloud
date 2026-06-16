# -*- coding: utf-8 -*-
"""
詳細ページの全リンク・全テーブル内容をダンプして、添付ファイルの場所を特定する。
読み取り専用。
"""
import sys
from playwright.sync_api import sync_playwright

URL = "https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115"

sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=200)
    page = browser.new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    try:
        page.get_by_role("button", name="同意する").first.click(timeout=3000)
    except Exception:
        pass

    page.locator("#case-name").fill("解体")
    page.locator("input#OAA0102").click()
    page.wait_for_load_state("networkidle")

    page.get_by_role("link", name="公示本文").first.click()
    page.wait_for_load_state("networkidle")

    print("=== 全リンク ===")
    for el in page.locator("a").all():
        text = (el.text_content() or "").strip()
        href = el.get_attribute("href")
        onclick = el.get_attribute("onclick")
        if text or href or onclick:
            print(f"text='{text}' href={href} onclick={onclick}")

    print("\n=== 全テーブルの行（先頭セルのみ） ===")
    tables = page.locator("table")
    for i in range(tables.count()):
        t = tables.nth(i)
        rows = t.locator("tr")
        rc = rows.count()
        if rc == 0:
            continue
        print(f"--- table {i} (rows={rc}) ---")
        for r in range(rc):
            cells = rows.nth(r).locator("th, td")
            cc = cells.count()
            texts = []
            for c in range(cc):
                txt = (cells.nth(c).inner_text() or "").strip().replace("\n", " / ")
                texts.append(txt[:60])
            print(texts)

    print("\n操作確認のため40秒間ブラウザを開いたままにします...")
    page.wait_for_timeout(40000)
    browser.close()
