"""
spike/93_pportal_detail.py

「公示本文」リンク（procurementItemInfoId指定）の遷移先を確認する。
構造化された詳細ページか、PDFへの直リンクかを見る。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "pportal"
OUT_DIR.mkdir(parents=True, exist_ok=True)


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

        print("[1] 検索画面→検索実行（東京法務局旧調布出張所を再現）")
        page.goto("https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115",
                   wait_until="networkidle", timeout=30000)
        page.locator("input[name='searchConditionBean.caseDivision'][value='0']").check()
        page.locator("input[name='searchConditionBean.articleNm']").fill("解体")
        page.locator("input[name='OAA0102']").click()
        page.wait_for_load_state("networkidle", timeout=30000)

        print("[2] 「東京法務局旧調布出張所」の行の「公示本文」リンクをクリック")
        row = page.locator("tr", has_text="東京法務局旧調布出張所").first
        link = row.locator("a.koukoku").first
        print(f"  href/onclick確認中...")

        try:
            with ctx.expect_page(timeout=8000) as popup_info:
                link.click()
            popup = popup_info.value
            popup.wait_for_load_state("networkidle", timeout=20000)
            print(f"  → 新タブで開いた: {popup.url}")
            shot(popup, "04_koukoku_popup")
            save_html(popup, "04_koukoku_popup")
        except Exception as e:
            print(f"  新タブでは開かず: {e}")
            page.wait_for_load_state("networkidle", timeout=15000)
            print(f"  → 現在のURL: {page.url}")
            shot(page, "04_koukoku_same")
            save_html(page, "04_koukoku_same")

        browser.close()


if __name__ == "__main__":
    main()
