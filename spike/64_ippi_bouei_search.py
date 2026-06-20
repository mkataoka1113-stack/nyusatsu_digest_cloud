"""
spike/64_ippi_bouei_search.py

発注機関=国の機関/防衛省、工事の業種=解体工事(29) で実際に検索を実行し、
結果件数・内容を確認する。あわせてネットワーク通信を記録してAPI的なエンドポイントの
有無を確認する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_bouei_dump.txt", "w", encoding="utf-8")
requests_log = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1200})

    def on_request(req):
        if req.resource_type in ("xhr", "fetch", "document") and "i-ppi.jp" in req.url:
            requests_log.append(f"{req.method} {req.url}")

    page.on("request", on_request)

    page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
    contents = page.frame(name="contents")
    contents.evaluate("__doPostBack('lbtKojiKokoku','')")
    page.wait_for_timeout(1500)
    page.wait_for_load_state("networkidle")

    # 発注機関 大分類=国の機関(0)
    page.select_option("#drpTopKikanInf", "0")
    page.wait_for_timeout(1500)
    page.wait_for_load_state("networkidle")

    # 中分類の選択肢を確認
    mid_opts = [(o.get_attribute("value"), o.inner_text()) for o in page.locator("#drpLargeKikanInf2 option").all()]
    out.write(f"中分類選択肢: {mid_opts}\n")

    # 防衛省を選択（value文字列を特定）
    bouei_value = None
    for v, t in mid_opts:
        if "防衛省" in t:
            bouei_value = v
            break
    out.write(f"防衛省 value={bouei_value}\n")

    if bouei_value:
        page.select_option("#drpLargeKikanInf2", bouei_value)
        page.wait_for_timeout(1000)

    # 工事の業種=解体工事(29)
    page.select_option("#drpKojiGyosyu", "29")
    page.wait_for_timeout(500)

    # 表示件数を100件に
    page.select_option("#drpCount", "100")

    # 検索開始
    page.click("#btnSearch")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    page.screenshot(path="spike/screenshots/ippi/04_bouei_result.png", full_page=True)
    with open("spike/screenshots/ippi/04_bouei_result.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    out.write(f"\n結果ページURL: {page.url}\n")
    body_text = page.inner_text("body")
    out.write(f"\n本文抜粋(先頭3000文字):\n{body_text[:3000]}\n")

    out.write("\n--- ネットワークリクエスト(主要) ---\n")
    for r in requests_log[-30:]:
        out.write(r + "\n")

    browser.close()

out.close()
