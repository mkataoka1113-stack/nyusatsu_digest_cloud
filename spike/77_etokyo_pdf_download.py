"""e-tokyo: 詳細ページの公告文PDFをダウンロードしてテキスト抽出できるか確認する"""
import io
import re
import sys
import time
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pypdf
from playwright.sync_api import sync_playwright

FRAMESET_URL = "https://www.e-tokyo.lg.jp/choutatu_ppij/ppij/pub"
GYOSHU_CODE = "3100"


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
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
    page = ctx.new_page()

    today = datetime.now()
    since = today - timedelta(days=30)

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

    link = None
    for row in main.query_selector_all("table.list-table tbody tr"):
        link = row.query_selector("td.list-data-akname a")
        if link:
            break
    link.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(1.5)
    main = next((f for f in page.frames if f.name == "FrmMain"), None)

    # 「公告文」リンクをクリック → download or popup を検証
    kokoku = main.query_selector('a[href*="openFile"]:has-text("公告文")')
    if not kokoku:
        # :has-text が query_selector で使えない場合に備えたフォールバック
        for a in main.query_selector_all("a"):
            if "公告文" in (a.inner_text() or ""):
                kokoku = a
                break
    print("公告文リンク:", kokoku.get_attribute("href"))

    try:
        with page.expect_download(timeout=20000) as dl_info:
            kokoku.click()
        dl = dl_info.value
        path = dl.path()
        print("ダウンロード成功:", dl.suggested_filename)
        with open(path, "rb") as fh:
            data = fh.read()
        print("サイズ:", len(data))
        r = pypdf.PdfReader(io.BytesIO(data))
        txt = "".join(p.extract_text() or "" for p in r.pages)
        print("ページ数:", len(r.pages), "文字数:", len(txt))
        print("=== 先頭800字 ===")
        print(txt[:800])
        # 目的キーワードの有無
        for kw in ["予定価格", "参加資格", "本店", "所在", "工期"]:
            print(f"  「{kw}」含む: {kw in txt}")
    except Exception as e:
        print("expect_downloadでは取れず:", e)
        # ポップアップの可能性を確認
        print("open pages:", [p.url[:80] for p in ctx.pages])

    browser.close()
print("完了")
