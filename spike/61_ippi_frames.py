"""
spike/61_ippi_frames.py

i-ppi.jp のフレーム構成（contents=Map.aspx, main=Right_form.htm）を個別に開いて
中身（地域選択・検索フォーム）を確認する。
"""
import sys
from playwright.sync_api import sync_playwright

CONTENTS_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Top/Map.aspx"
MAIN_URL     = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Top/Right_form.htm"

out = open("spike/ippi_frames_dump.txt", "w", encoding="utf-8")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)

    for label, url in [("contents", CONTENTS_URL), ("main", MAIN_URL)]:
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.screenshot(path=f"spike/screenshots/ippi/02_{label}.png", full_page=True)
        with open(f"spike/screenshots/ippi/02_{label}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        out.write(f"=== {label} ===\n")
        out.write("text snippet: " + page.inner_text("body")[:800].replace("\n", " / ") + "\n")
        links = page.locator("a").all()
        out.write(f"  links: {len(links)}\n")
        for l in links[:40]:
            try:
                out.write(f"    {l.inner_text().strip()!r} -> {l.get_attribute('href')}\n")
            except Exception:
                pass
        selects = page.locator("select").all()
        out.write(f"  selects: {len(selects)}\n")
        for s in selects:
            try:
                name = s.get_attribute("name")
                opts = [o.inner_text() for o in s.locator("option").all()]
                out.write(f"   select name={name} options(first15)={opts[:15]}\n")
            except Exception:
                pass
        inputs = page.locator("input").all()
        out.write(f"  inputs: {len(inputs)}\n")
        for i in inputs[:20]:
            try:
                out.write(f"   input name={i.get_attribute('name')} type={i.get_attribute('type')} value={i.get_attribute('value')}\n")
            except Exception:
                pass
        page.close()

    browser.close()

out.close()
