"""JKK: 詳細リンククリック後の遷移を詳しく調査する（新ウィンドウ/同一ページ更新の判別）"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.to-kousya.or.jp/keiyaku/nyusatu/index.html"
CATEGORY_ID = "015"
OUT = r"C:\Users\masak\AppData\Local\Temp\claude\C--Users-masak-Desktop------300-------998-claude-workspace\4a870af1-daad-4ea9-a11d-7729f15fbb0d\scratchpad"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
    page = ctx.new_page()

    page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
    with ctx.expect_page(timeout=15000) as popup_info:
        page.locator("a", has_text="電子入札公表・結果").first.click()
    bid = popup_info.value
    bid.wait_for_load_state("networkidle", timeout=30000)

    bid.select_option('select[name="categoryId"]', CATEGORY_ID)
    bid.locator("input#btnSearch").click()
    bid.wait_for_load_state("networkidle", timeout=30000)
    bid.wait_for_timeout(500)

    first = bid.locator('a[id^="linkNo_"]').first
    auc_id = first.get_attribute("id")
    print("クリック対象:", auc_id)
    # onclick属性やhrefの中身を確認
    print("href:", first.get_attribute("href"))
    print("onclick:", first.get_attribute("onclick"))
    # イベントリスナー経由かもしれないので、周辺のscriptを探す
    html = bid.content()
    with open(OUT + r"\jkk_search_page.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    # linkNo_ を含むscript部分を表示
    import re
    for m in re.finditer(r".{200}linkNo.{400}", html, re.S):
        print("--- linkNo周辺 ---")
        print(m.group(0)[:650])
        break

    # 新ページが開くか試す
    try:
        with ctx.expect_page(timeout=8000) as detail_info:
            first.click()
        detail = detail_info.value
        detail.wait_for_load_state("networkidle", timeout=30000)
        print("新ウィンドウで開いた:", detail.url[:100])
        body = detail.inner_text("body")
    except Exception as e:
        print("新ウィンドウは開かず:", type(e).__name__)
        bid.wait_for_timeout(3000)
        try:
            bid.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        print("現在URL:", bid.url[:100])
        body = bid.inner_text("body")

    with open(OUT + r"\jkk_detail_body2.txt", "w", encoding="utf-8") as fh:
        fh.write(body)
    print("本文文字数:", len(body))
    print(body[:2000])
    browser.close()
print("完了")
