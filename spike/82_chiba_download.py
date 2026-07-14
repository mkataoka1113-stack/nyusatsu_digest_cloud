"""ちば電子調達: 詳細ページから入札公告zipをダウンロードし、中のPDFをテキスト化できるか確認する"""
import io
import sys
import time
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pypdf
from playwright.sync_api import sync_playwright

ENTRY_URL = "https://www.chiba-ep-bis.supercals.jp/ebidPPIPublish/EjPPIj"


def wait_main(page, predicate_js, timeout_sec=15):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        frame = next((f for f in page.frames if f.name == "mainfrm"), None)
        if frame:
            try:
                if frame.evaluate(predicate_js):
                    return frame
            except Exception:
                pass
        time.sleep(0.3)
    return None


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 1200}, accept_downloads=True)
    page = ctx.new_page()

    page.goto(ENTRY_URL, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(1500)
    menu = next(f for f in page.frames if f.name == "menu_Frm")
    menu.locator("a", has_text="入札予定(公告)").first.click()
    page.wait_for_timeout(2000)

    cond = next(f for f in page.frames if f.name == "cond")
    cond.evaluate("""() => {
        document.frm.ChoutatsuCD.value = '00';
        document.frm.KoujiSyubetu.value = '0010290';
        document.frm.ejMaxDisplayRowCount.value = '100';
        document.frm.submit();
    }""")
    page.wait_for_timeout(3000)

    lst = next(f for f in page.frames if f.name == "list")
    lst.locator('a[onclick*="openYotei"]').nth(0).click()
    main = wait_main(page, "() => !!document.querySelector('td.INPUT_TITLE_L_L')")

    # 添付ファイル名一覧
    files = main.evaluate("""() => {
        const out = [];
        for (let i = 1; i <= 10; i++) {
            const el = document.downloadForm['AddInfoURL' + String(i).padStart(2, '0')];
            if (el && el.value) out.push({idx: i, name: el.value});
        }
        return out;
    }""")
    print("添付ファイル:", files)

    # 「公告」を含むファイルをダウンロード
    target = next((f for f in files if "公告" in f["name"]), files[0] if files else None)
    if not target:
        print("添付なし")
        browser.close()
        sys.exit()
    print("ダウンロード対象:", target)

    try:
        with page.expect_download(timeout=30000) as dl_info:
            main.evaluate(f"downloadStart({target['idx']})")
        dl = dl_info.value
        print("ダウンロード成功:", dl.suggested_filename)
        with open(dl.path(), "rb") as fh:
            data = fh.read()
        print("サイズ:", len(data))
        if target["name"].lower().endswith(".zip"):
            zf = zipfile.ZipFile(io.BytesIO(data))
            print("zip内容:", zf.namelist())
            for n in zf.namelist():
                if n.lower().endswith(".pdf"):
                    pdf_data = zf.read(n)
                    r = pypdf.PdfReader(io.BytesIO(pdf_data))
                    txt = "".join(p.extract_text() or "" for p in r.pages)
                    print(f"--- {n}: {len(r.pages)}頁 {len(txt)}字 ---")
                    print(txt[:600])
                    for kw in ["予定価格", "参加資格", "所在", "地域"]:
                        print(f"  「{kw}」含む: {kw in txt}")
                    break
        elif target["name"].lower().endswith(".pdf"):
            r = pypdf.PdfReader(io.BytesIO(data))
            txt = "".join(p.extract_text() or "" for p in r.pages)
            print(f"{len(r.pages)}頁 {len(txt)}字")
            print(txt[:600])
    except Exception as e:
        print("ダウンロード失敗:", e)

    browser.close()
print("完了")
