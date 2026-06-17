"""
spike/53_chiba_koukoku.py

menu_Frmの「入札予定(公告)」をクリックし、mainfrmに表示される検索画面の構造を調査する。
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
        page.wait_for_timeout(2500)

        print("フレーム一覧（クリック後）:")
        for f in page.frames:
            print(f"  name={f.name!r} url={f.url[:100]}")

        cond = next(f for f in page.frames if f.name == "cond")
        lst  = next(f for f in page.frames if f.name == "list")
        print(f"cond url={cond.url}")
        print(f"list url={lst.url}")
        (OUT_DIR / "20_koukoku.png").write_bytes(page.screenshot(full_page=True))
        (OUT_DIR / "20_cond.html").write_text(cond.content(), encoding="utf-8")
        (OUT_DIR / "20_list.html").write_text(lst.content(), encoding="utf-8")

        print("\n--- cond body text ---")
        print(cond.locator("body").inner_text()[:2500])

        print("\n--- cond select 一覧 ---")
        for sel in cond.locator("select").all():
            name = sel.get_attribute("name") or sel.get_attribute("id") or ""
            opts = sel.locator("option").all()
            print(f"  select name/id={name!r} option数={len(opts)}")
            for o in opts[:15]:
                print(f"    value={o.get_attribute('value')!r} text={o.inner_text().strip()!r}")

        print("\n--- KoujiSyubetu 全選択肢 ---")
        for o in cond.locator('select[name="KoujiSyubetu"] option').all():
            print(f"    value={o.get_attribute('value')!r} text={o.inner_text().strip()!r}")

        print("\n--- list body text ---")
        print(lst.locator("body").inner_text()[:2500])

        print("\n--- cond 内ボタン一覧 ---")
        for b in cond.locator('input[type="button"], input[type="submit"], button').all():
            print(f"  tag value={b.get_attribute('value')!r} onclick={(b.get_attribute('onclick') or '')[:100]!r}")

        browser.close()


if __name__ == "__main__":
    main()
