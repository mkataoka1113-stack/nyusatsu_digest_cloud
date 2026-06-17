"""
spike/55_chiba_detail.py

検索結果の「表示」リンク（openYotei）をクリックし、詳細画面の構造（一意ID・公告日等）を調査する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "chiba"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENTRY_URL = "https://www.chiba-ep-bis.supercals.jp/ebidPPIPublish/EjPPIj"


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1200})
        page = ctx.new_page()
        page.goto(ENTRY_URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(1500)

        menu = next(f for f in page.frames if f.name == "menu_Frm")
        menu.locator("a", has_text="入札予定(公告)").first.click()
        page.wait_for_timeout(2000)

        cond = next(f for f in page.frames if f.name == "cond")
        cond.evaluate("""() => {
            document.frm.ChoutatsuCD.value = '00';
            document.frm.KoujiSyubetu.value = '0010290';
            document.frm.submit();
        }""")
        page.wait_for_timeout(3000)

        lst = next(f for f in page.frames if f.name == "list")
        print("[1] 「表示」リンクをクリック")
        lst.locator('a[onclick*="openYotei"]').first.click()
        page.wait_for_timeout(2000)

        print("\nフレーム一覧:")
        for f in page.frames:
            print(f"  name={f.name!r} url={f.url[:110]}")

        # 詳細はmainfrmに直接読み込まれた可能性があるので両方試す
        for fname in ["list", "mainfrm"]:
            detail = next((f for f in page.frames if f.name == fname), None)
            if detail:
                try:
                    (OUT_DIR / f"40_detail_{fname}.html").write_text(detail.content(), encoding="utf-8")
                    print(f"\n--- detail ({fname}) body text ---")
                    print(detail.locator("body").inner_text(timeout=5000)[:3000])
                except Exception as e:
                    print(f"  {fname}: {e}")

        (OUT_DIR / "40_detail.png").write_bytes(page.screenshot(full_page=True))
        print(f"\nページURL: {page.url}")

        browser.close()


if __name__ == "__main__":
    main()
