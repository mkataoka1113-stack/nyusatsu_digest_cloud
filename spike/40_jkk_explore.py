"""
spike/40_jkk_explore.py

JKK東京 入札情報ページから「電子入札公表・結果」をクリックした先を調査する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "jkk"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_URL = "https://www.to-kousya.or.jp/keiyaku/nyusatu/index.html"


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

        print("[1] 入札情報ページを開く")
        page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
        shot(page, "01_top")

        print("\n[2] ページ内の「電子入札公表・結果」関連リンクを列挙")
        links = page.locator("a").all()
        for lnk in links:
            try:
                text = lnk.inner_text().strip()
                href = lnk.get_attribute("href") or ""
                target = lnk.get_attribute("target") or ""
                if "公表" in text or "結果" in text or "電子入札" in text:
                    print(f"    [{text}] href={href} target={target}")
            except Exception:
                pass

        print("\n[3] 「電子入札公表・結果」テキストを含むリンクをクリック")
        target_link = page.locator("a", has_text="電子入札公表・結果").first
        if target_link.count() == 0:
            print("  該当リンクが見つかりません")
            browser.close()
            return

        href = target_link.get_attribute("href")
        print(f"  href={href}")

        try:
            with ctx.expect_page(timeout=8000) as popup_info:
                target_link.click()
            popup = popup_info.value
            popup.wait_for_load_state("networkidle", timeout=30000)
            print(f"  → 新タブで開いた: {popup.url}")
            shot(popup, "02_clicked_popup")
            save_html(popup, "02_clicked_popup")
        except Exception:
            page.wait_for_load_state("networkidle", timeout=15000)
            print(f"  → 同タブで遷移: {page.url}")
            shot(page, "02_clicked_same")
            save_html(page, "02_clicked_same")

        browser.close()


if __name__ == "__main__":
    main()
