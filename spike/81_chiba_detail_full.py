"""ちば電子調達: 詳細ページの全ラベル・添付リンクを確認する"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

ENTRY_URL = "https://www.chiba-ep-bis.supercals.jp/ebidPPIPublish/EjPPIj"
OUT = r"C:\Users\masak\AppData\Local\Temp\claude\C--Users-masak-Desktop------300-------998-claude-workspace\4a870af1-daad-4ea9-a11d-7729f15fbb0d\scratchpad"


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
    count = lst.locator('a[onclick*="openYotei"]').count()
    print("結果件数:", count)

    lst.locator('a[onclick*="openYotei"]').nth(0).click()
    main = wait_main(page, "() => !!document.querySelector('td.INPUT_TITLE_L_L')")

    data = main.evaluate("""() => {
        const result = {};
        document.querySelectorAll('td.INPUT_TITLE_L_L').forEach(td => {
            const label = td.innerText.trim();
            const val = td.nextElementSibling ? td.nextElementSibling.innerText.trim() : '';
            if (label) result[label] = val;
        });
        return result;
    }""")
    print("=== 全ラベル ===")
    for k, v in data.items():
        print(f"  {k}: {v[:80]}")

    body = main.inner_text("body")
    with open(OUT + r"\chiba_detail_body.txt", "w", encoding="utf-8") as fh:
        fh.write(body)
    print("本文文字数:", len(body))

    print("=== リンク・ボタン一覧 ===")
    for a in main.query_selector_all("a, input[type=button], input[type=submit]"):
        t = (a.inner_text() or a.get_attribute("value") or "").strip()
        h = a.get_attribute("href") or ""
        oc = a.get_attribute("onclick") or ""
        if t:
            print(f"  [{t[:35]}] href={h[:60]} onclick={oc[:70]}")

    main_html = main.content()
    with open(OUT + r"\chiba_detail.html", "w", encoding="utf-8") as fh:
        fh.write(main_html)
    page.screenshot(path=OUT + r"\chiba_detail.png", full_page=True)
    browser.close()
print("完了")
