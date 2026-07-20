"""
spike/90_pportal_explore.py

政府電子調達等システム 調達ポータル（p-portal.go.jp）のトップページ構造・
案件検索の可否・ログイン要否を調査する。
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

        print("[1] トップページを開く")
        try:
            page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"  goto失敗: {e}")
            page.goto(TOP_URL, timeout=30000)
            page.wait_for_timeout(3000)
        print(f"  URL: {page.url}")
        shot(page, "01_top")
        save_html(page, "01_top")

        print("\n[2] ページ内のリンク一覧（案件検索・入札公告関連）")
        links = page.locator("a").all()
        for lnk in links:
            try:
                text = lnk.inner_text().strip()
                href = lnk.get_attribute("href") or ""
                if not text:
                    continue
                if any(kw in text for kw in ["調達", "入札", "検索", "案件", "公告", "ログイン", "資格"]):
                    print(f"    [{text}] href={href}")
            except Exception:
                pass

        print("\n[3] フレーム構成の確認")
        for f in page.frames:
            print(f"    frame: name={f.name!r} url={f.url}")

        browser.close()


if __name__ == "__main__":
    main()
