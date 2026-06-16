# -*- coding: utf-8 -*-
"""
「解体」検索結果一覧から、各案件行のリンク・ボタン(公示本文・入札等)の構造を確認する。
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

    print("=== 検索後URL ===")
    print(page.url)

    # 全テーブルの行数とヘッダーらしき内容をざっと見る
    tables = page.locator("table")
    n = tables.count()
    print(f"table数: {n}")
    for i in range(n):
        t = tables.nth(i)
        rows = t.locator("tr")
        rc = rows.count()
        if rc >= 2:
            first_row_text = rows.nth(0).inner_text().replace("\n", " | ")
            second_row_text = rows.nth(1).inner_text().replace("\n", " | ")
            if "調達案件" in first_row_text or "調達案件" in second_row_text:
                print(f"\n--- table {i} (rows={rc}) ---")
                for r in range(min(rc, 4)):
                    print(f"行{r}: {rows.nth(r).inner_text().replace(chr(10), ' | ')}")
                # このテーブル内のリンク・ボタンを確認
                print("  -- リンク/ボタン --")
                for el in t.locator("a, button, input[type=submit], input[type=button]").all():
                    text = (el.text_content() or "").strip()
                    tag = el.evaluate("e => e.tagName")
                    href = el.get_attribute("href")
                    name = el.get_attribute("name")
                    value = el.get_attribute("value")
                    if text or href:
                        print(f"  tag={tag} text='{text}' href={href} name={name} value={value}")

    print("\n操作確認のため30秒間ブラウザを開いたままにします...")
    page.wait_for_timeout(30000)
    browser.close()
