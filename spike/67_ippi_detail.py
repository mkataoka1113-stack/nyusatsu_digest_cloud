"""
spike/67_ippi_detail.py

検索結果の1件をクリックして詳細画面の構造を確認する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_detail_dump.txt", "w", encoding="utf-8")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1200})
    page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
    contents = page.frame(name="contents")
    contents.evaluate("__doPostBack('lbtKojiKokoku','')")
    page.wait_for_timeout(1500)
    page.wait_for_load_state("networkidle")

    page.select_option("#drpTopKikanInf", "0")
    page.wait_for_timeout(1000)
    page.select_option("#drpLargeKikanInf2", "05")
    page.wait_for_timeout(1000)
    page.select_option("#drpKojiGyosyu", "29")
    page.check("#rbtKokokuDate2Kokoku")
    page.fill("#dateKokokuFromKokoku", "2026-06-12")
    page.fill("#dateKokokuToKokoku", "2026-06-20")
    page.click("#btnSearch")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    # 結果テーブルのリンクを確認
    links = page.locator("table a").all()
    out.write(f"table内リンク数: {len(links)}\n")
    for l in links[:10]:
        try:
            out.write(f"  {l.inner_text().strip()!r} -> {l.get_attribute('href')}\n")
        except Exception:
            pass

    # 1件目をクリック（工事名のリンクと思われる）
    first_link = page.locator("table a").first
    first_link.click()
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    page.screenshot(path="spike/screenshots/ippi/07_detail.png", full_page=True)
    with open("spike/screenshots/ippi/07_detail.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    out.write("\n=== 詳細ページ ===\n")
    out.write(f"URL: {page.url}\n")
    out.write(page.inner_text("body")[:4000] + "\n")

    browser.close()

out.close()
