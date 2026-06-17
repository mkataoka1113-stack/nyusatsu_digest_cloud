"""
spike/56_chiba_loop.py

検索結果の全件について「表示」→詳細抽出→「戻る」を繰り返すループを検証する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "chiba"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENTRY_URL = "https://www.chiba-ep-bis.supercals.jp/ebidPPIPublish/EjPPIj"


def extract_detail(frame) -> dict:
    return frame.evaluate("""() => {
        const result = {};
        document.querySelectorAll('td.INPUT_TITLE_L_L').forEach(td => {
            const label = td.innerText.trim();
            const val = td.nextElementSibling ? td.nextElementSibling.innerText.trim() : '';
            if (label) result[label] = val;
        });
        return result;
    }""")


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
        count = lst.locator('a[onclick*="openYotei"]').count()
        print(f"件数: {count}")

        for i in range(count):
            lst = next(f for f in page.frames if f.name == "list")
            print(f"\n--- index {i} ---")
            lst.locator('a[onclick*="openYotei"]').nth(i).click()
            page.wait_for_timeout(1500)

            main_frame = next(f for f in page.frames if f.name == "mainfrm")
            data = extract_detail(main_frame)
            for k, v in data.items():
                print(f"  {k}: {v}")

            # 戻る
            page.evaluate("top.mainfrm.document.nextfrm.submit()")
            page.wait_for_timeout(1500)

        browser.close()


if __name__ == "__main__":
    main()
