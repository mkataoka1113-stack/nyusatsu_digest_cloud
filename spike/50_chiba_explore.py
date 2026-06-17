"""
spike/50_chiba_explore.py

ちば電子調達システム（chibaepportal.supercals.jp）の画面構造を探索する。
SPA（JS動的読み込み）のため、networkidleまで待ってから内容を確認する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "chiba"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_URL = "https://chibaepportal.supercals.jp/vendor_portal_index"


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

        print("[1] トップページを開く")
        page.goto(TOP_URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2000)
        shot(page, "01_top")
        save_html(page, "01_top")
        print(f"  url={page.url}")

        print("\n[2] body テキスト（先頭2000文字）")
        print(page.locator("body").inner_text()[:2000])

        print("\n[3] リンク一覧")
        links = page.locator("a").all()
        print(f"  リンク数={len(links)}")
        for lnk in links[:60]:
            try:
                text = lnk.inner_text().strip()
                href = lnk.get_attribute("href") or ""
                if text or href:
                    print(f"    [{text}] href={href}")
            except Exception:
                pass

        print("\n[4] ボタン一覧")
        btns = page.locator("button").all()
        print(f"  ボタン数={len(btns)}")
        for b in btns[:60]:
            try:
                text = b.inner_text().strip()
                if text:
                    print(f"    [{text}]")
            except Exception:
                pass

        browser.close()


if __name__ == "__main__":
    main()
