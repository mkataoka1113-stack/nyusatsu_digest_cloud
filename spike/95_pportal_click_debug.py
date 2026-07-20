"""
spike/95_pportal_click_debug.py

pportal.py の抽出ロジックがうまく動かない原因を切り分けるためのデバッグ。
クリック直後のURL・inner_text構造を確認する。
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
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()

        page.goto("https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115",
                   wait_until="networkidle", timeout=30000)
        page.locator("input[name='searchConditionBean.caseDivision'][value='0']").check()
        page.locator("input[name='searchConditionBean.articleNm']").fill("解体")
        page.locator("input[name='searchConditionBean.publicStartDateFrom']").fill(since)
        page.locator("input[name='OAA0102']").click()
        page.wait_for_load_state("networkidle", timeout=30000)
        print("results URL:", page.url)

        links = page.locator("a.koukoku")
        print("koukoku count:", links.count())
        link = links.nth(0)
        href = link.get_attribute("href")
        print("href:", href)

        print("--- clicking ---")
        link.click()
        page.wait_for_timeout(3000)
        print("URL right after click+wait3s:", page.url)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print("networkidle wait failed:", e)
        print("URL after networkidle wait:", page.url)

        shot = OUT_DIR / "06_after_click.png"
        page.screenshot(path=str(shot), full_page=True)
        (OUT_DIR / "06_after_click.html").write_text(page.content(), encoding="utf-8")

        body = page.inner_text("body")
        print("body length:", len(body))
        print("body[:500]:")
        print(body[:500])

        browser.close()


if __name__ == "__main__":
    main()
