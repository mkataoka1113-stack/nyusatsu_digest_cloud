"""
spike/33_tokyometro_category2.py

業種選択ポップアップ（ComCategorySelect.jsp）で「その他工事」(004)を展開し、
解体工事の業種コードを特定する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "tokyometro"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PBI_URL = "https://www.e-procurement.metro.tokyo.lg.jp/indexPbi.jsp"
CAT_URL = (
    "https://www.e-procurement.metro.tokyo.lg.jp/ComCategorySelect.jsp"
    "?formName=main&categElm=TextgyosyuCd&categCdHdElm=gyosyuNm"
    "&gyomuType=1&elmVolume=10&categoryKbnCd=&selectCategory="
    "&categCdElm=gyosyuCd&categoryCdArea=constKbnCd"
    "&selectCategoryArea=selectConst&gamenId=hacchuyotei"
)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1000, "height": 800})
        main_page = ctx.new_page()
        main_page.goto(PBI_URL, wait_until="networkidle", timeout=30000)
        main_page.evaluate("SelectTargetSubmit(3, 3, '_top')")
        main_page.wait_for_load_state("networkidle", timeout=30000)
        print(f"main_page url={main_page.url}")

        page = ctx.new_page()
        page.goto(CAT_URL, wait_until="networkidle", timeout=30000)
        print(f"url={page.url}")
        print(f"select数={page.locator('select').count()}")
        (OUT_DIR / "31_debug.html").write_text(page.content(), encoding="utf-8")

        for code, label in [("001", "土木・建築工事"), ("004", "その他工事"), ("099", "特殊工事")]:
            print(f"\n[展開] preCategory={code} ({label})")
            page.select_option('select[name="preCategory"]', code)
            page.evaluate("changeDisp(document.forms[0], 'preCategory')")
            page.wait_for_timeout(500)
            opts = page.locator('select[name="preCategory"] option').all()
            for o in opts:
                txt = o.inner_text().strip()
                if "解体" in txt or txt.startswith("　") or txt.startswith(" "):
                    print(f"    value={o.get_attribute('value')!r} text={txt!r}")
            # 全件出力（デバッグ用）
            print("  --- 全option ---")
            for o in opts:
                print(f"    value={o.get_attribute('value')!r} text={o.inner_text().strip()!r}")

        browser.close()


if __name__ == "__main__":
    main()
