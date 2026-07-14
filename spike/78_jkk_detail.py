"""JKK: 検索結果1件目の詳細ページを開き、テキスト・PDFリンクを確認する"""
import io
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pypdf
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
    # 案件状態は指定せず全件（受付中が0件でも詳細構造を確認するため）
    bid.locator("input#btnSearch").click()
    bid.wait_for_load_state("networkidle", timeout=30000)
    bid.wait_for_timeout(500)

    links = bid.locator('a[id^="linkNo_"]')
    print("結果件数:", links.count())
    if links.count() == 0:
        print("0件のため終了")
        browser.close()
        sys.exit()

    first = links.first
    print("1件目ID:", first.get_attribute("id"))
    first.click()
    bid.wait_for_load_state("networkidle", timeout=30000)
    bid.wait_for_timeout(1000)

    print("詳細URL:", bid.url[:100])
    body = bid.inner_text("body")
    with open(OUT + r"\jkk_detail_body.txt", "w", encoding="utf-8") as fh:
        fh.write(body)
    print("本文文字数:", len(body))
    print("=== 本文先頭2500字 ===")
    print(body[:2500])
    print("=== リンク一覧 ===")
    for a in bid.locator("a").all():
        try:
            t = (a.inner_text() or "").strip()
            h = a.get_attribute("href") or ""
            oc = a.get_attribute("onclick") or ""
            if t and (h or oc):
                print(f"  [{t[:35]}] href={h[:80]} onclick={oc[:60]}")
        except Exception:
            pass
    bid.screenshot(path=OUT + r"\jkk_detail.png", full_page=True)
    browser.close()
print("完了")
