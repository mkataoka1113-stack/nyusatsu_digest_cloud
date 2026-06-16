# -*- coding: utf-8 -*-
"""
「調達情報の検索」ページで、件名に「解体」と入力して検索を実行し、
検索結果一覧の構造(件数・各行のリンク・列構成)を確認する。
読み取り専用（検索ボタンを押すのみ。データの変更は行わない）。
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

    # クッキー同意バナーが出たら「同意する」を押す
    try:
        page.get_by_role("button", name="同意する").first.click(timeout=3000)
    except Exception:
        pass

    # 件名欄に「解体」を入力
    page.locator("#case-name").fill("解体")

    # 検索ボタンをクリック
    page.locator("input#OAA0102").click()
    page.wait_for_load_state("networkidle")

    print("=== 検索後のURL ===")
    print(page.url)
    print("=== ページタイトル ===")
    print(page.title())

    # 結果件数らしきテキストを探す
    print("\n=== '件' を含むテキスト ===")
    body_text = page.locator("body").inner_text()
    for line in body_text.splitlines():
        line = line.strip()
        if line and ("件" in line or "結果" in line):
            print(repr(line))

    print("\n=== テーブル構造 ===")
    tables = page.locator("table")
    print(f"table数: {tables.count()}")
    for i in range(min(tables.count(), 3)):
        t = tables.nth(i)
        print(f"--- table {i} ---")
        rows = t.locator("tr")
        for r in range(min(rows.count(), 5)):
            cells = rows.nth(r).locator("th, td")
            texts = [(cells.nth(c).inner_text() or "").strip().replace("\n", " / ") for c in range(cells.count())]
            print(texts)

    print("\n操作確認のため30秒間ブラウザを開いたままにします...")
    page.wait_for_timeout(30000)
    browser.close()
