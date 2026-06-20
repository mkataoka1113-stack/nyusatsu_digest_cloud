"""
spike/68_ippi_detail2.py

館山（８）車庫等解体工事 の行をクリックして詳細画面を確認する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_detail2_dump.txt", "w", encoding="utf-8")

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

    page.click("text=館山（８）車庫等解体工事")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    page.screenshot(path="spike/screenshots/ippi/08_detail2.png", full_page=True)
    with open("spike/screenshots/ippi/08_detail2.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    out.write(f"URL: {page.url}\n")
    out.write(page.inner_text("body")[:5000] + "\n")

    # 添付ファイルや外部リンクの確認
    links = page.locator("a").all()
    out.write(f"\nリンク数: {len(links)}\n")
    for l in links:
        try:
            t = l.inner_text().strip()
            h = l.get_attribute("href")
            if t or (h and "javascript" not in (h or "")):
                out.write(f"  {t!r} -> {h}\n")
        except Exception:
            pass

    browser.close()

out.close()
