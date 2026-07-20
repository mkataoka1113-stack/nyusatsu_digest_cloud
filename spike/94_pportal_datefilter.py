"""
spike/94_pportal_datefilter.py

公開開始日の自/至での絞り込みが機能するか確認する。
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "pportal"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    since = (datetime.now() - timedelta(days=8)).strftime("%Y/%m/%d")
    print(f"since={since}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        page.goto("https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115",
                   wait_until="networkidle", timeout=30000)
        page.locator("input[name='searchConditionBean.caseDivision'][value='0']").check()
        page.locator("input[name='searchConditionBean.articleNm']").fill("解体")
        page.locator("input[name='searchConditionBean.publicStartDateFrom']").fill(since)
        page.locator("input[name='OAA0102']").click()
        page.wait_for_load_state("networkidle", timeout=30000)
        print(f"URL: {page.url}")

        body_text = page.inner_text("body")
        for line in body_text.split("\n"):
            line = line.strip()
            if "件見つかりました" in line or "入力エラー" in line or "エラー" in line:
                print(f"  {line}")

        p = OUT_DIR / "05_datefilter.png"
        page.screenshot(path=str(p), full_page=True)
        (OUT_DIR / "05_datefilter.html").write_text(page.content(), encoding="utf-8")
        print("saved")

        browser.close()


if __name__ == "__main__":
    main()
