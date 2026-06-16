# -*- coding: utf-8 -*-
"""
ご指定の条件（調達機関:防衛省/法務省/財務省/文部科学省、所在地:関東・甲信越、
品目分類:041.建設工事）で検索し、件数とタイトル一覧を確認する。
読み取り専用。
"""
import sys
from playwright.sync_api import sync_playwright

URL = "https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115"

sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=100)
    page = browser.new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    try:
        page.get_by_role("button", name="同意する").first.click(timeout=3000)
    except Exception:
        pass

    def check_via_label(name, value):
        eid = page.locator(f"input[name='{name}'][value='{value}']").get_attribute("id")
        page.locator(f"label[for='{eid}']").click(force=True)

    # 調達機関: 防衛省(010) 法務省(013) 財務省(015) 文部科学省(016)
    for value in ["010", "013", "015", "016"]:
        check_via_label("searchConditionBean.govementProcurementOraganBean.procurementOrgNm", value)

    # 所在地: 関東・甲信越 (area3)
    check_via_label("searchConditionBean.govementProcurementOraganBean.area", "3")

    # 品目分類: 041.建設工事
    check_via_label("searchConditionBean.itemClassifcationBean.itemClassifcation", "041")

    page.locator("input#OAA0102").click()
    page.wait_for_load_state("networkidle")

    print("=== 検索後URL ===")
    print(page.url)

    body_text = page.locator("body").inner_text()
    for line in body_text.splitlines():
        line = line.strip()
        if "件見つかりました" in line:
            print(line)

    # 結果テーブル(table 3相当)から案件名を抽出
    tables = page.locator("table")
    for i in range(tables.count()):
        t = tables.nth(i)
        rows = t.locator("tr")
        rc = rows.count()
        if rc >= 2:
            header = rows.nth(0).inner_text().replace("\n", " | ")
            if "調達案件名称" in header:
                print(f"\n--- table {i} (rows={rc}) ---")
                for r in range(1, min(rc, 30)):
                    cells = rows.nth(r).locator("th, td")
                    texts = [(cells.nth(c).inner_text() or "").strip().replace("\n", " / ") for c in range(cells.count())]
                    print(texts[:4])

    browser.close()
