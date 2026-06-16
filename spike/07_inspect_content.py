# -*- coding: utf-8 -*-
"""
詳細ページの「公告内容」セルの全文を確認する。
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

    # 「公告内容」行を探す
    rows = page.locator("table").first.locator("tr")
    for r in range(rows.count()):
        cells = rows.nth(r).locator("th, td")
        if cells.count() >= 2:
            header = (cells.nth(0).inner_text() or "").strip()
            if header == "公告内容":
                content = cells.nth(1).inner_text()
                print("=== 公告内容 全文 ===")
                print(content)
                print(f"\n(文字数: {len(content)})")

    browser.close()
