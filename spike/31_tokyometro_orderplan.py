"""
spike/31_tokyometro_orderplan.py

入札情報サービス画面で「発注予定情報」(SelectTargetSubmit(3,3,'_top')) をクリックした先の
画面構造（検索フォーム・結果テーブル）を調査する。
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


def dump_form(page, label: str):
    forms = page.locator("form").all()
    print(f"  [{label}] form数: {len(forms)}")
    for f in forms:
        name = f.get_attribute("name") or ""
        action = f.get_attribute("action") or ""
        print(f"    form name={name!r} action={action!r}")
        for inp in f.locator("input,select,textarea").all()[:60]:
            tag = inp.evaluate("e => e.tagName")
            iname = inp.get_attribute("name") or ""
            ival = inp.get_attribute("value") or ""
            print(f"      {tag} name={iname!r} value={ival!r}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        print("[1] 入札情報サービス画面を開く")
        page.goto(PBI_URL, wait_until="networkidle", timeout=30000)
        dump_form(page, "indexPbi")

        print("\n[2] 「発注予定情報」(page=3, act=3) をクリック")
        page.evaluate("SelectTargetSubmit(3, 3, '_top')")
        page.wait_for_load_state("networkidle", timeout=30000)
        shot(page, "11_orderplan")
        save_html(page, "11_orderplan")
        print(f"  url={page.url}")
        dump_form(page, "orderplan")

        # ページ内のテキストも一部出力（どんな画面か把握するため）
        body_text = page.locator("body").inner_text()
        print("\n  --- body text (先頭1500文字) ---")
        print(body_text[:1500])

        browser.close()


if __name__ == "__main__":
    main()
