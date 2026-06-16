# -*- coding: utf-8 -*-
"""
検索結果の1件目の「公示本文」リンクをクリックし、
詳細ページの構造(添付PDFへのリンク等)を確認する。
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

    # 1件目の「公示本文」リンクをクリック
    page.get_by_role("link", name="公示本文").first.click()
    page.wait_for_load_state("networkidle")

    print("=== 詳細ページURL ===")
    print(page.url)
    print("=== ページタイトル ===")
    print(page.title())

    print("\n=== PDF/添付ファイルらしきリンク ===")
    for el in page.locator("a").all():
        text = (el.text_content() or "").strip()
        href = el.get_attribute("href")
        onclick = el.get_attribute("onclick")
        combined = f"{href or ''} {onclick or ''}"
        if ".pdf" in combined.lower() or "ファイル" in text or "添付" in text or "Download" in combined or "download" in combined.lower():
            print(f"text='{text}' href={href} onclick={onclick}")

    print("\n=== ページ内の主要見出し(h1〜h3) ===")
    for el in page.locator("h1, h2, h3").all():
        print((el.text_content() or "").strip())

    print("\n操作確認のため40秒間ブラウザを開いたままにします...")
    page.wait_for_timeout(40000)
    browser.close()
