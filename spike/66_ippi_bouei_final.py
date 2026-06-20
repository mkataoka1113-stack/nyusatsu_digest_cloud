"""
spike/66_ippi_bouei_final.py

発注機関=防衛省、工事の業種=解体工事(29)、公告日=直近8日間 で検索し、
習志野・館山の案件が正しく絞り込めるか最終確認する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_bouei_final_dump.txt", "w", encoding="utf-8")

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

    # 工事の業種=解体工事
    page.select_option("#drpKojiGyosyu", "29")

    # 公告日: 期間指定、2026-06-12 ～ 2026-06-20
    page.check("#rbtKokokuDate2Kokoku")
    page.fill("#dateKokokuFromKokoku", "2026-06-12")
    page.fill("#dateKokokuToKokoku", "2026-06-20")

    page.select_option("#drpCount", "100")
    page.click("#btnSearch")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    page.screenshot(path="spike/screenshots/ippi/06_bouei_kaitai_8days.png", full_page=True)
    with open("spike/screenshots/ippi/06_bouei_kaitai_8days.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    out.write(page.inner_text("body")[:3000] + "\n")

    browser.close()

out.close()
