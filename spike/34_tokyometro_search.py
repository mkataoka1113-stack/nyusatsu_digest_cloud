"""
spike/34_tokyometro_search.py

業種=解体工事(3101)を選択した状態で検索を実行し、結果一覧の構造（テーブル・ページネーション）を調査する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "tokyometro"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PBI_URL = "https://www.e-procurement.metro.tokyo.lg.jp/indexPbi.jsp"


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

        page.goto(PBI_URL, wait_until="networkidle", timeout=30000)
        page.evaluate("SelectTargetSubmit(3, 3, '_top')")
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(800)
        print(f"[1] 発注予定検索画面 url={page.url}")

        print("[2] 業種選択ポップアップで解体工事(3101)を選択")
        with ctx.expect_page(timeout=30000) as popup_info:
            page.locator("a", has_text="業種の").first.click()
        popup = popup_info.value
        popup.wait_for_load_state("networkidle", timeout=30000)
        popup.select_option('select[name="preCategory"]', "004")
        popup.evaluate("changeDisp(document.forms[0], 'preCategory')")
        popup.wait_for_timeout(300)
        popup.select_option('select[name="preCategory"]', "3101")
        popup.locator('input[type="button"][value=" 選択 >> "]').click()
        popup.wait_for_timeout(300)
        popup.locator('a.btnS', has_text="選択").click()
        page.wait_for_timeout(500)

        gyosyu = page.eval_on_selector('[name="gyosyuCd"]', "el => el.value")
        print(f"  gyosyuCd={gyosyu!r}")

        print("\n[3] 検索ボタンをクリック")
        search_btn = page.locator("a, input", has_text="検索").last
        # 検索リンクの onclick を確認
        links = page.locator("a", has_text="検索").all()
        for l in links:
            print(f"  link text={l.inner_text().strip()!r} onclick={l.get_attribute('onclick')}")

        page.locator("a", has_text="検索").last.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(500)
        print(f"  url={page.url}")
        shot(page, "13_search_result")
        save_html(page, "13_search_result")

        body_text = page.locator("body").inner_text()
        print("\n  --- body text (先頭2500文字) ---")
        print(body_text[:2500])

        browser.close()


if __name__ == "__main__":
    main()
