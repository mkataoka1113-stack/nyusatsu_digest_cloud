"""
spike/54_chiba_submit.py

condフォーム(name="frm")を直接JSでsubmitし、解体工事(0010290)で検索した結果(listフレーム)を調査する。
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

        print("[1] 調達区分=工事、工事種別=解体工事(0010290) をセットして送信")
        cond.evaluate("""() => {
            document.frm.ChoutatsuCD.value = '00';
            document.frm.KoujiSyubetu.value = '0010290';
            document.frm.submit();
        }""")
        page.wait_for_timeout(3000)

        lst = next(f for f in page.frames if f.name == "list")
        print(f"list url={lst.url}")
        (OUT_DIR / "30_result.png").write_bytes(page.screenshot(full_page=True))
        (OUT_DIR / "30_result.html").write_text(lst.content(), encoding="utf-8")

        print("\n--- list body text ---")
        print(lst.locator("body").inner_text()[:3000])

        browser.close()


if __name__ == "__main__":
    main()
