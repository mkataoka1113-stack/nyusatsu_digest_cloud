"""
spike/51_chiba_bidinfo.py

「入札情報サービス」セクションの「工事・測量」カード（発注機関選択→こちら）を操作し、
遷移先の画面構造を調査する。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = Path(__file__).parent / "screenshots" / "chiba"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_URL = "https://chibaepportal.supercals.jp/vendor_portal_index"


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
        ctx = browser.new_context(viewport={"width": 1400, "height": 1200})
        page = ctx.new_page()

        page.goto(TOP_URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(1500)

        print("[1] 「入札情報サービス」の見出しを探す")
        heading = page.locator("text=入札情報サービス").first
        heading.scroll_into_view_if_needed()
        shot(page, "01_bidinfo_section")

        print("\n[2] 入札情報サービス内の「工事・測量」カードを探す")
        # 入札情報サービスの見出し以降にある最初の「工事・測量」カードを対象にする
        card = page.locator("div.vendor-bidding-information-service-c-s-widget").first
        print(f"  card count={card.count()}")
        if card.count() == 0:
            print("  カードが見つかりません。HTML保存して終了")
            save_html(page, "01_bidinfo_section")
            browser.close()
            return

        print("\n  --- カード内テキスト ---")
        print(card.inner_text())

        print("\n[3] 発注機関セレクトボックスの選択肢")
        select = card.locator("select").first
        print(f"  select count={select.count()}")
        if select.count() > 0:
            opts = select.locator("option").all()
            for o in opts[:20]:
                print(f"    value={o.get_attribute('value')!r} text={o.inner_text().strip()!r}")

        print("\n[4] ボタン一覧（カード内）")
        btns = card.locator("button").all()
        for b in btns:
            print(f"    [{b.inner_text().strip()}] disabled={b.get_attribute('disabled')}")

        browser.close()


if __name__ == "__main__":
    main()
