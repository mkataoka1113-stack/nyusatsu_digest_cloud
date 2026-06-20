"""
spike/63_ippi_search_form.py

入札公告等を検索（工事）の検索条件画面のフォーム構造を確認する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_form_dump.txt", "w", encoding="utf-8")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1200})
    page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
    contents = page.frame(name="contents")
    contents.evaluate("__doPostBack('lbtKojiKokoku','')")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    page.screenshot(path="spike/screenshots/ippi/03_search_form.png", full_page=True)
    with open("spike/screenshots/ippi/03_search_form.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    selects = page.locator("select").all()
    out.write(f"selects: {len(selects)}\n")
    for s in selects:
        try:
            sid = s.get_attribute("id")
            name = s.get_attribute("name")
            opts = [(o.get_attribute("value"), o.inner_text()) for o in s.locator("option").all()]
            out.write(f"select id={sid} name={name}\n")
            for v, t in opts[:30]:
                out.write(f"    value={v!r} text={t!r}\n")
        except Exception as e:
            out.write(f"ERROR reading select: {e}\n")

    inputs = page.locator("input").all()
    out.write(f"\ninputs: {len(inputs)}\n")
    for i in inputs[:60]:
        try:
            out.write(f"  input id={i.get_attribute('id')} name={i.get_attribute('name')} type={i.get_attribute('type')} value={i.get_attribute('value')}\n")
        except Exception:
            pass

    browser.close()

out.close()
