"""
調達ポータル(p-portal.go.jp)のトップページを開き、
「調達情報検索」へのリンク・ボタンの構造を調べるスパイクスクリプト。
読み取り専用。クリック等の操作はまだ行わない。
"""
from playwright.sync_api import sync_playwright

URL = "https://www.p-portal.go.jp/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=500)
    page = browser.new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    print("=== ページタイトル ===")
    print(page.title())

    print("\n=== '調達情報検索' を含むリンク/ボタン ===")
    for el in page.locator("a, button").all():
        text = (el.text_content() or "").strip()
        if "調達情報" in text or "検索" in text:
            tag = el.evaluate("e => e.tagName")
            href = el.get_attribute("href")
            onclick = el.get_attribute("onclick")
            print(f"- tag={tag} text='{text}' href={href} onclick={onclick}")

    print("\n操作確認のため15秒間ブラウザを開いたままにします...")
    page.wait_for_timeout(15000)
    browser.close()
