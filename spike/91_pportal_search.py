"""
spike/91_pportal_search.py

調達ポータルの「調達情報検索」画面の構造（検索条件・件名キーワード検索の
可否・結果一覧の列構成）を調査する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "pportal"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_URL = "https://www.p-portal.go.jp/"


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

        print("[1] 「調達情報検索」画面へ直接遷移")
        page.goto("https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115",
                   wait_until="networkidle", timeout=30000)
        print(f"  URL: {page.url}")
        shot(page, "02_search_top")
        save_html(page, "02_search_top")

        print("\n[2] フォーム内の入力項目を列挙")
        inputs = page.locator("input").all()
        for inp in inputs:
            try:
                name = inp.get_attribute("name") or ""
                itype = inp.get_attribute("type") or ""
                value = inp.get_attribute("value") or ""
                if name:
                    print(f"    input name={name!r} type={itype!r} value={value!r}")
            except Exception:
                pass

        selects = page.locator("select").all()
        for sel in selects:
            try:
                name = sel.get_attribute("name") or ""
                if name:
                    print(f"    select name={name!r}")
            except Exception:
                pass

        print("\n[3] 「件名」的なキーワード入力欄を探す")
        labels = page.locator("label, th, td").all()
        for lb in labels[:80]:
            try:
                text = lb.inner_text().strip()
                if text and len(text) < 30:
                    print(f"    label/th: {text}")
            except Exception:
                pass

        browser.close()


if __name__ == "__main__":
    main()
