"""
spike/60_ippi_explore.py

i-ppi.jp（統合PPI 入札情報サービス、JACIC運営）のトップページ構造を調査する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
    print("URL:", page.url)
    print("TITLE:", page.title())

    page.screenshot(path="spike/screenshots/ippi/01_top.png", full_page=True)
    with open("spike/screenshots/ippi/01_top.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    # frame構成を確認
    print("\n--- frames ---")
    for fr in page.frames:
        print(fr.name, fr.url)

    # リンク一覧
    print("\n--- links ---")
    links = page.locator("a").all()
    for l in links[:50]:
        try:
            print(repr(l.inner_text().strip()), "->", l.get_attribute("href"))
        except Exception:
            pass

    browser.close()
