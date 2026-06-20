"""
spike/69_ippi_backtest.py

詳細画面から history.back() で一覧に戻り、次の行をクリックできるか検証する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_backtest_dump.txt", "w", encoding="utf-8")

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
    page.fill("#dateKokokuFromKokoku", "2026-04-01")
    page.fill("#dateKokokuToKokoku", "2026-06-20")
    page.select_option("#drpCount", "100")
    page.click("#btnSearch")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    count = page.locator("#dgrSearchList tr").count() - 1  # ヘッダ行を除く
    out.write(f"list rows: {count}\nurl_before: {page.url}\n")

    for i in range(min(count, 3)):
        try:
            out.write(f"-- index {i} --\n")
            page.evaluate(f"__doPostBack('dgrSearchList','${i}')")
            page.wait_for_timeout(2500)
            page.wait_for_load_state("networkidle")
            out.write(f"[{i}] url_after_click: {page.url}\n")
            body = page.inner_text("body")
            out.write(f"[{i}] has_kouji_gaiyo: {'案件概要' in body}\n")
            idx = body.find("工事名称")
            if idx >= 0:
                out.write(f"[{i}] 工事名称付近: {body[idx:idx+100]!r}\n")

            page.go_back()
            page.wait_for_timeout(2000)
            page.wait_for_load_state("networkidle")
            out.write(f"[{i}] url_after_back: {page.url}\n")
            check_count = page.locator("#dgrSearchList tr").count() - 1
            out.write(f"[{i}] after go_back, list rows visible: {check_count}\n")
        except Exception as e:
            out.write(f"[{i}] ERROR: {e}\n")

    browser.close()

out.close()
