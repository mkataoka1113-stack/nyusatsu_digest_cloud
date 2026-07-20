"""
spike/92_pportal_search_kaitai.py

調達ポータルで「調達案件名称=解体」「公開中の調達案件」「入札公告(公示)」
のみで検索し、結果一覧の構造・件数・詳細ページの日付情報を確認する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "pportal"
OUT_DIR.mkdir(parents=True, exist_ok=True)


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

        print("[1] 検索画面を開く")
        page.goto("https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115",
                   wait_until="networkidle", timeout=30000)

        print("[2] 「公開中の調達案件」を選択し、案件名称に「解体」を入力")
        page.locator("input[name='searchConditionBean.caseDivision'][value='0']").check()
        page.locator("input[name='searchConditionBean.articleNm']").fill("解体")

        print("[3] 検索実行")
        page.locator("input[name='OAA0102']").click()
        page.wait_for_load_state("networkidle", timeout=30000)
        print(f"  URL: {page.url}")
        shot(page, "03_search_result")
        save_html(page, "03_search_result")

        print("\n[4] 結果件数・一覧構造の確認")
        body_text = page.inner_text("body")
        for line in body_text.split("\n"):
            line = line.strip()
            if "件" in line and any(c.isdigit() for c in line) and len(line) < 40:
                print(f"    {line}")

        print("\n[5] 結果テーブルらしき要素の行数")
        rows = page.locator("table tr").all()
        print(f"    table tr count: {len(rows)}")
        for r in rows[:15]:
            try:
                text = r.inner_text().replace("\n", " | ").strip()
                if text:
                    print(f"    row: {text[:150]}")
            except Exception:
                pass

        browser.close()


if __name__ == "__main__":
    main()
