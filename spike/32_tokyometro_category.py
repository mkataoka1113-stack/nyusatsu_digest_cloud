"""
spike/32_tokyometro_category.py

発注予定情報検索画面の「業種の一覧表」ポップアップ（openSubWindow → ComCategorySelect.jsp）を開き、
解体工事（業種コード）を選択する操作フローを調査する。
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
        page.wait_for_timeout(1000)
        print(f"[1] 発注予定検索画面 url={page.url}")

        print("[2] 「業種の一覧表」リンクをクリックしてポップアップを開く")
        with ctx.expect_page(timeout=30000) as popup_info:
            page.locator("a", has_text="業種の").first.click()
        popup = popup_info.value
        popup.wait_for_load_state("networkidle", timeout=30000)
        print(f"  popup url={popup.url}")
        shot(popup, "21_category_popup")
        save_html(popup, "21_category_popup")

        print("\n  --- popup body text (先頭2000文字) ---")
        print(popup.locator("body").inner_text()[:2000])

        # 業種一覧の <select>/<a>/<option> 要素を列挙
        print("\n  --- select 要素 ---")
        for sel in popup.locator("select").all():
            name = sel.get_attribute("name") or ""
            opts = sel.locator("option").all()
            print(f"  select name={name!r} option数={len(opts)}")
            for o in opts[:60]:
                print(f"    value={o.get_attribute('value')!r} text={o.inner_text().strip()!r}")

        print("\n[3] 「その他工事」(004) を展開し、解体工事(3101)を選択して追加")
        popup.select_option('select[name="preCategory"]', "004")
        popup.evaluate("changeDisp(document.forms[0], 'preCategory')")
        popup.wait_for_timeout(300)
        popup.select_option('select[name="preCategory"]', "3101")
        popup.locator('input[type="button"][value=" 選択 >> "]').click()
        popup.wait_for_timeout(300)
        opts2 = popup.locator('select[name="selectedCategory"] option').all()
        print(f"  selectedCategory option数={len(opts2)}")
        for o in opts2:
            print(f"    value={o.get_attribute('value')!r} text={o.inner_text().strip()!r}")
        shot(popup, "22_category_selected")

        print("\n[4] 「選択」リンクをクリックして親フォームに反映 → ポップアップを閉じる")
        popup.locator('a.btnS', has_text="選択").click()
        page.wait_for_timeout(500)

        print("\n  --- main page のフォーム値（業種関連） ---")
        for name in ["TextgyosyuCd", "gyosyuCd", "gyosyuNm", "constKbnCd", "selectConst"]:
            try:
                val = page.eval_on_selector(f'[name="{name}"]', "el => el.value")
                print(f"    {name} = {val!r}")
            except Exception as e:
                print(f"    {name}: 取得失敗 {e}")

        shot(page, "12_after_category")
        save_html(page, "12_after_category")

        browser.close()


if __name__ == "__main__":
    main()
