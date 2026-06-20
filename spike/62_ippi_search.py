"""
spike/62_ippi_search.py

i-ppi.jp の詳細検索（入札公告等を検索）で
発注機関=国の機関/防衛省、工事の業種=解体工事業 を指定して検索し、
実際に結果が取得できるか確認する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_search_dump.txt", "w", encoding="utf-8")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1200})
    page.goto(TOP_URL, wait_until="networkidle", timeout=30000)

    # フレームセット内の contents フレームを取得
    contents = page.frame(name="contents")
    out.write(f"contents frame found: {contents is not None}\n")

    # 「入札公告等を検索」（工事検索側）リンクをクリック -> __doPostBack('lbtKojiKokoku','')
    contents.evaluate("__doPostBack('lbtKojiKokoku','')")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    out.write(f"after click, page.url={page.url}\n")
    for fr in page.frames:
        out.write(f"frame: {fr.name} {fr.url}\n")

    browser.close()

out.close()
