"""
spike/41_jkk_search.py

JKK東京の公表・入札結果検索画面で、業種=解体・案件状態=入札参加受付中で検索し、
結果一覧の構造を調査する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "jkk"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_URL = "https://www.to-kousya.or.jp/keiyaku/nyusatu/index.html"


def shot(page, name: str):
    p = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(p), full_page=True)
    print(f"  [screenshot] {p.name}")


def save_html(page, name: str):
    p = OUT_DIR / f"{name}.html"
    p.write_text(page.content(), encoding="utf-8")
    print(f"  [html] {p.name}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.goto(TOP_URL, wait_until="networkidle", timeout=30000)

        target_link = page.locator("a", has_text="電子入札公表・結果").first
        with ctx.expect_page(timeout=15000) as popup_info:
            target_link.click()
        bid = popup_info.value
        bid.wait_for_load_state("networkidle", timeout=30000)
        print(f"[1] 公表・入札結果画面 url={bid.url}")

        print("\n[2] categoryId の選択肢を列挙し、「解体」を探す")
        opts = bid.locator('select[name="categoryId"] option').all()
        kaitai_value = None
        for o in opts:
            text = o.inner_text().strip()
            val = o.get_attribute("value")
            if text == "解体":
                kaitai_value = val
            print(f"    value={val!r} text={text!r}")

        print(f"\n  解体 の value = {kaitai_value!r}")
        if not kaitai_value:
            print("  解体が見つからないため終了")
            browser.close()
            return

        print("\n[3] 業種=解体、案件状態=全て を選択して検索（まずは件数の有無を確認）")
        bid.select_option('select[name="categoryId"]', kaitai_value)
        bid.select_option('select[name="selbidStatus"]', "all")
        bid.locator('input#btnSearch').click()
        bid.wait_for_load_state("networkidle", timeout=30000)
        bid.wait_for_timeout(500)
        print(f"  url={bid.url}")
        shot(bid, "11_search_result")
        save_html(bid, "11_search_result")

        print("\n  --- body text (先頭3000文字) ---")
        print(bid.locator("body").inner_text()[:3000])

        browser.close()


if __name__ == "__main__":
    main()
