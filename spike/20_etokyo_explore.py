"""
spike/20_etokyo_explore.py

東京都電子調達サービス (https://www.e-tokyo.lg.jp/) の画面構造を探索する。
スクリーンショットと HTML を spike/screenshots/etokyo/ に保存する。

■ 初回のみ（インストール）
  pip install playwright
  playwright install chromium

■ 実行
  python spike/20_etokyo_explore.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR  = Path(__file__).parent / "screenshots" / "etokyo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_URL  = "https://www.e-tokyo.lg.jp/choutatu_ppij/cmn/tmg/cmn/jsp/indexQ.jsp"
PUB_URL  = "https://www.e-tokyo.lg.jp/choutatu_ppij/ppij/pub"


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
        browser = pw.chromium.launch(headless=False, slow_mo=500)
        ctx  = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        # ── Step 1: サービストップ ──────────────────────────────────
        print("\n[1] サービストップを開く")
        page.goto(TOP_URL, wait_until="networkidle")
        shot(page, "01_top")
        save_html(page, "01_top")

        # ── Step 2: フレームセット本体 ──────────────────────────────
        print("\n[2] 入札情報フレームセット")
        page.goto(PUB_URL, wait_until="networkidle")
        shot(page, "02_frameset")

        # フレーム一覧を表示
        print(f"  フレーム数: {len(page.frames)}")
        for i, f in enumerate(page.frames):
            print(f"    frame[{i}]: url={f.url}")

        # ── Step 3: 各フレームを直接開いて探索 ─────────────────────
        for s in ["P001", "P002", "P003", "P004", "P005"]:
            for a in ["1", "2"]:
                url = f"{PUB_URL}?s={s}&a={a}"
                print(f"\n[3] {url}")
                try:
                    page.goto(url, wait_until="networkidle", timeout=10000)
                    shot(page, f"03_{s}_a{a}")
                    save_html(page, f"03_{s}_a{a}")
                except Exception as e:
                    print(f"  ⚠ {e}")

        # ── Step 4: 左ナビから「入札公告」を探してクリック ─────────
        print("\n[4] 左ナビ (s=P001&a=1) で入札公告リンクを探す")
        page.goto(f"{PUB_URL}?s=P001&a=1", wait_until="networkidle")
        links = page.locator("a").all()
        print(f"  リンク数: {len(links)}")
        for lnk in links:
            try:
                text = lnk.inner_text().strip()
                href = lnk.get_attribute("href") or ""
                if text:
                    print(f"    [{text}] → {href}")
            except Exception:
                pass

        print("\n完了。screenshots/etokyo/ を確認してください。")
        input("Enterを押してブラウザを閉じる > ")
        browser.close()


if __name__ == "__main__":
    main()
