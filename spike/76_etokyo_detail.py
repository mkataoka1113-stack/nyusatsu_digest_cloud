"""e-tokyo: 検索結果1件目の詳細ページを開き、テキスト・リンク・PDF有無を確認する"""
import re
import sys
import time
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

FRAMESET_URL = "https://www.e-tokyo.lg.jp/choutatu_ppij/ppij/pub"
GYOSHU_CODE = "3100"
OUT = r"C:\Users\masak\AppData\Local\Temp\claude\C--Users-masak-Desktop------300-------998-claude-workspace\4a870af1-daad-4ea9-a11d-7729f15fbb0d\scratchpad"


def wait_frame(page, name, selector, timeout_sec=20):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        frame = next((f for f in page.frames if f.name == name), None)
        if frame:
            el = frame.query_selector(selector)
            if el:
                return frame
        time.sleep(0.5)
    return None


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()

    today = datetime.now()
    since = today - timedelta(days=30)  # 広めに取って確実に1件ヒットさせる

    page.goto(FRAMESET_URL, wait_until="networkidle", timeout=30000)
    page.evaluate("""() => {
        const f = document.createElement('form');
        f.method = 'post'; f.action = 'pub'; f.target = 'FrmMain';
        const add = (n, v) => { const i = document.createElement('input');
            i.type = 'hidden'; i.name = n; i.value = v; f.appendChild(i); };
        add('s', 'P002'); add('a', '1');
        document.body.appendChild(f); f.submit();
    }""")
    main = wait_frame(page, "FrmMain", 'select[name="year"]')
    main.evaluate("""() => { document.querySelectorAll('input[name="govCode"]').forEach(cb => cb.checked = true); }""")
    main.select_option('select[name="year"]', str(today.year))
    main.evaluate(f"""() => {{
        const set = (name, val) => {{ const el = document.querySelector('[name="' + name + '"]'); if (el) el.value = val; }};
        set('categoryCode', '{GYOSHU_CODE}'); set('constKbnCd', '{GYOSHU_CODE}');
        set('selectConst', '{GYOSHU_CODE} 解体工事'); set('TextgyosyuCd', ' 解体工事');
    }}""")
    main.fill('input[name="pubStDate"]', since.strftime("%Y%m%d"))
    main.fill('input[name="pubEndDate"]', today.strftime("%Y%m%d"))
    main.evaluate("""() => {
        const f = document.forms['main'] || document.querySelector('form');
        f.target = '_self';
        const setHidden = (name, val) => { let el = f.querySelector('[name="' + name + '"]');
            if (!el) { el = document.createElement('input'); el.type = 'hidden'; el.name = name; f.appendChild(el); }
            el.value = val; };
        setHidden('s', 'P002'); setHidden('a', '3'); f.submit();
    }""")
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(1)
    main = next((f for f in page.frames if f.name == "FrmMain"), None)

    rows = main.query_selector_all("table.list-table tbody tr")
    print(f"結果行数: {len(rows)}")
    link = None
    for row in rows:
        link = row.query_selector("td.list-data-akname a")
        if link:
            print("1件目:", link.inner_text().strip())
            break
    if not link:
        print("案件リンクなし")
        browser.close()
        sys.exit()

    # 詳細を開く（listSubmitはフレーム内JS）
    href = link.get_attribute("href") or ""
    print("href:", href)
    link.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(1.5)

    # 全フレームの状態を確認
    for f in page.frames:
        print("frame:", f.name, "|", f.url[:100])

    main = next((f for f in page.frames if f.name == "FrmMain"), None)
    body = main.inner_text("body")
    with open(OUT + r"\etokyo_detail_body.txt", "w", encoding="utf-8") as fh:
        fh.write(body)
    print("本文文字数:", len(body))
    print("=== 本文先頭2500字 ===")
    print(body[:2500])
    print("=== リンク一覧 ===")
    for a in main.query_selector_all("a"):
        t = (a.inner_text() or "").strip()
        h = a.get_attribute("href") or ""
        oc = a.get_attribute("onclick") or ""
        if t or h:
            print(f"  [{t[:30]}] href={h[:80]} onclick={oc[:80]}")
    main_html = main.content()
    with open(OUT + r"\etokyo_detail.html", "w", encoding="utf-8") as fh:
        fh.write(main_html)
    page.screenshot(path=OUT + r"\etokyo_detail.png", full_page=True)
    browser.close()
print("完了")
