"""
spike/52_chiba_frames.py

ちば電子調達システムの入札情報サービス（工事・測量）フレームセットの各フレーム内容を調査する。
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

        (OUT_DIR / "10_frameset.png").write_bytes(page.screenshot(full_page=True))

        for f in page.frames:
            if f == page.main_frame:
                continue
            print(f"\n=== frame name={f.name!r} url={f.url[:100]} ===")
            try:
                text = f.locator("body").inner_text(timeout=5000)
                print(text[:1500])
            except Exception as e:
                print(f"  (テキスト取得失敗: {e})")

            try:
                links = f.locator("a").all()
                print(f"  リンク数={len(links)}")
                for lnk in links[:40]:
                    t = lnk.inner_text().strip()
                    href = lnk.get_attribute("href") or ""
                    onclick = lnk.get_attribute("onclick") or ""
                    if t or onclick:
                        print(f"    [{t}] href={href[:50]} onclick={onclick[:90]}")
            except Exception as e:
                print(f"  (リンク取得失敗: {e})")

            (OUT_DIR / f"frame_{f.name or 'main'}.html").write_text(
                f.content() if hasattr(f, "content") else "", encoding="utf-8"
            )

        browser.close()


if __name__ == "__main__":
    main()
