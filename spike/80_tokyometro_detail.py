"""都庁本体: 発注予定情報の検索結果1件目の詳細を開き、内容を確認する"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

PBI_URL = "https://www.e-procurement.metro.tokyo.lg.jp/indexPbi.jsp"
GYOSHU_CODE = "3101"
OUT = r"C:\Users\masak\AppData\Local\Temp\claude\C--Users-masak-Desktop------300-------998-claude-workspace\4a870af1-daad-4ea9-a11d-7729f15fbb0d\scratchpad"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
    page = ctx.new_page()

    page.goto(PBI_URL, wait_until="networkidle", timeout=30000)
    page.evaluate("SelectTargetSubmit(3, 3, '_top')")
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(800)

    # 業種選択ポップアップ
    with ctx.expect_page(timeout=15000) as popup_info:
        page.locator("a", has_text="業種の").first.click()
    popup = popup_info.value
    popup.wait_for_load_state("networkidle", timeout=20000)
    popup.select_option('select[name="preCategory"]', "004")
    popup.evaluate("changeDisp(document.forms[0], 'preCategory')")
    popup.wait_for_timeout(300)
    popup.select_option('select[name="preCategory"]', GYOSHU_CODE)
    popup.locator('input[type="button"][value=" 選択 >> "]').click()
    popup.wait_for_timeout(300)
    popup.locator("a.btnS", has_text="選択").click()
    page.wait_for_timeout(500)

    page.locator("a", has_text="検索").last.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(500)

    rows = page.query_selector_all("table.list-data tbody tr")
    print("結果行数:", len(rows))
    link = None
    for row in rows:
        cells = row.query_selector_all("td")
        if len(cells) >= 11:
            link = cells[2].query_selector("a")
            if link:
                print("1件目:", link.inner_text().strip())
                break
    if not link:
        print("案件リンクなし")
        browser.close()
        sys.exit()

    link.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(1000)

    body = page.inner_text("body")
    with open(OUT + r"\tokyometro_detail_body.txt", "w", encoding="utf-8") as fh:
        fh.write(body)
    print("URL:", page.url[:100])
    print("本文文字数:", len(body))
    print("=== 本文 ===")
    print(body[:2500])
    print("=== リンク一覧 ===")
    for a in page.query_selector_all("a"):
        t = (a.inner_text() or "").strip()
        h = a.get_attribute("href") or ""
        if t and ("javascript" in h or ".pdf" in h.lower()):
            print(f"  [{t[:35]}] {h[:90]}")
    page.screenshot(path=OUT + r"\tokyometro_detail.png", full_page=True)
    browser.close()
print("完了")
