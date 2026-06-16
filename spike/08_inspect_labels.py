# -*- coding: utf-8 -*-
"""
検索フォーム内のチェックボックス(調達機関・所在地・品目分類)について、
id とそれに対応するラベルテキストの組を一覧化する。
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

    print("=== 調達機関 (procurementOrgNm) ===")
    for el in page.locator("input[name='searchConditionBean.govementProcurementOraganBean.procurementOrgNm']").all():
        eid = el.get_attribute("id")
        value = el.get_attribute("value")
        label_text = ""
        try:
            label_text = page.locator(f"label[for='{eid}']").first.inner_text()
        except Exception:
            pass
        print(f"id={eid} value={value} label='{label_text}'")

    print("\n=== 品目分類 (itemClassifcation) ===")
    for el in page.locator("input[name='searchConditionBean.itemClassifcationBean.itemClassifcation']").all():
        eid = el.get_attribute("id")
        value = el.get_attribute("value")
        label_text = ""
        try:
            label_text = page.locator(f"label[for='{eid}']").first.inner_text()
        except Exception:
            pass
        print(f"id={eid} value={value} label='{label_text}'")

    print("\n=== 所在地エリア (govementProcurementOraganBean.area) ===")
    for el in page.locator("input[name='searchConditionBean.govementProcurementOraganBean.area']").all():
        eid = el.get_attribute("id")
        value = el.get_attribute("value")
        label_text = ""
        try:
            label_text = page.locator(f"label[for='{eid}']").first.inner_text()
        except Exception:
            pass
        print(f"id={eid} value={value} label='{label_text}'")

    browser.close()
