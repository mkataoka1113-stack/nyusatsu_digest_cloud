"""
spike/22_etokyo_debug.py
結果ページのHTML構造を確認するデバッグスクリプト
"""
import time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

FRAMESET_URL = "https://www.e-tokyo.lg.jp/choutatu_ppij/ppij/pub"
GYOSHU_CODE  = "3100"

today     = datetime.now()
since     = today - timedelta(days=30)
date_to   = today.strftime("%Y%m%d")
date_from = since.strftime("%Y%m%d")


def wait_form(page, fname, sel, timeout_sec=20):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        fr = next((f for f in page.frames if f.name == fname), None)
        if fr and fr.query_selector(sel):
            return fr
        time.sleep(0.5)
    return None


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx  = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()

    page.goto(FRAMESET_URL, wait_until="networkidle", timeout=30000)
    print(f"フレーム数: {len(page.frames)}")

    page.evaluate("""() => {
        const f = document.createElement('form');
        f.method = 'post';
        f.action = 'pub';
        f.target = 'FrmMain';
        const add = (n, v) => {
            const i = document.createElement('input');
            i.type = 'hidden'; i.name = n; i.value = v;
            f.appendChild(i);
        };
        add('s', 'P002');
        add('a', '1');
        document.body.appendChild(f);
        f.submit();
    }""")

    mf = wait_form(page, "FrmMain", 'select[name="year"]', 20)
    if not mf:
        print("ERROR: P002 form not found in FrmMain")
        browser.close()
        exit(1)
    print(f"FrmMain URL: {mf.url}")

    mf.evaluate("""() => {
        document.querySelectorAll('input[name="govCode"]')
            .forEach(cb => cb.checked = true);
    }""")
    mf.select_option('select[name="year"]', str(today.year))
    mf.evaluate(f"""() => {{
        const set = (name, val) => {{
            const el = document.querySelector('[name="' + name + '"]');
            if (el) el.value = val;
        }};
        set('categoryCode', '{GYOSHU_CODE}');
        set('constKbnCd',   '{GYOSHU_CODE}');
        set('selectConst',  '{GYOSHU_CODE} 解体工事');
        set('TextgyosyuCd', ' 解体工事');
    }}""")
    mf.fill('input[name="pubStDate"]', date_from)
    mf.fill('input[name="pubEndDate"]', date_to)

    mf.evaluate("""() => {
        const f = document.forms['main'] || document.querySelector('form');
        if (!f) { console.error('no form'); return; }
        f.target = '_self';
        const setH = (name, val) => {
            let el = f.querySelector('[name="' + name + '"]');
            if (!el) {
                el = document.createElement('input');
                el.type = 'hidden'; el.name = name;
                f.appendChild(el);
            }
            el.value = val;
        };
        setH('s', 'P002');
        setH('a', '3');
        f.submit();
    }""")

    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(1)

    mf2 = next((f for f in page.frames if f.name == "FrmMain"), None)
    print(f"結果ページ URL: {mf2.url if mf2 else 'None'}")

    html = mf2.content()

    # list-table の周辺を確認
    idx = html.find("list-table")
    if idx >= 0:
        print("\n=== list-table found at", idx, "===")
        print(html[max(0, idx - 50): idx + 600])
    else:
        print("list-table NOT FOUND")

    # list-line の確認
    idx2 = html.find("list-line")
    if idx2 >= 0:
        print("\n=== list-line found ===")
        print(html[max(0, idx2 - 100): idx2 + 500])
    else:
        print("list-line NOT FOUND")

    # 直接テーブル行を取得
    rows = mf2.query_selector_all("table.list-table tbody tr")
    print(f"\ntr 要素数 (table.list-table tbody): {len(rows)}")

    rows_all = mf2.query_selector_all("table tbody tr")
    print(f"tr 要素数 (全 table tbody): {len(rows_all)}")

    # count の確認
    count_el = mf2.query_selector("td.list-count-disp")
    print(f"件数表示: {count_el.inner_text().strip() if count_el else '(なし)'}")

    browser.close()
