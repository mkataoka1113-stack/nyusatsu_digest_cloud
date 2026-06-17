"""
spike/30_tokyometro_explore.py

東京都電子調達システム（都庁本体・入札情報サービス）
https://www.e-procurement.metro.tokyo.lg.jp/ の画面構造を探索する。
スクリーンショットと HTML を spike/screenshots/tokyometro/ に保存する。

■ 初回のみ（インストール）
  pip install playwright
  playwright install chromium

■ 実行
  python spike/30_tokyometro_explore.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR  = Path(__file__).parent / "screenshots" / "tokyometro"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_URL = "https://www.e-procurement.metro.tokyo.lg.jp/index.jsp"
PBI_URL = "https://www.e-procurement.metro.tokyo.lg.jp/indexPbi.jsp"


def shot(page, name: str):
    p = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(p), full_page=True)
    print(f"  [screenshot] {p.name}")


def save_html(page, name: str):
    p = OUT_DIR / f"{name}.html"
    p.write_text(page.content(), encoding="utf-8")
    print(f"  [html] {p.name}")


def dump_frames(page, prefix: str):
    print(f"  フレーム数: {len(page.frames)}")
    for i, f in enumerate(page.frames):
        print(f"    frame[{i}]: name={f.name!r} url={f.url}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx  = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        # ── Step 1: トップページ ──────────────────────────────────
        print("\n[1] トップページを開く")
        page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
        shot(page, "01_top")
        save_html(page, "01_top")
        dump_frames(page, "01")

        # ── Step 2: 入札情報サービス（indexPbi.jsp） ───────────────
        print("\n[2] 入札情報サービス画面")
        page.goto(PBI_URL, wait_until="networkidle", timeout=30000)
        shot(page, "02_pbi")
        save_html(page, "02_pbi")
        dump_frames(page, "02")

        # ── Step 3: 各フレームのリンクを列挙 ───────────────────────
        print("\n[3] 各フレーム内のリンクを列挙")
        for i, f in enumerate(page.frames):
            try:
                links = f.locator("a").all()
            except Exception as e:
                print(f"  frame[{i}] リンク取得失敗: {e}")
                continue
            print(f"  frame[{i}] name={f.name!r} url={f.url[:90]} リンク数={len(links)}")
            for lnk in links[:40]:
                try:
                    text = lnk.inner_text().strip()
                    href = lnk.get_attribute("href") or ""
                    onclick = lnk.get_attribute("onclick") or ""
                    if text or onclick:
                        print(f"      [{text}] href={href[:60]} onclick={onclick[:80]}")
                except Exception:
                    pass

        print("\n完了。spike/screenshots/tokyometro/ を確認してください。")
        browser.close()


if __name__ == "__main__":
    main()
