"""
spike/65_ippi_bouei_search2.py

掲載期間（公告日）が当日のみに絞られていた疑いがあるため、
ラジオボタンの状態を確認し、期間指定なし or 広い期間にして再検索する。
"""
from playwright.sync_api import sync_playwright

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"

out = open("spike/ippi_bouei2_dump.txt", "w", encoding="utf-8")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1200})
    page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
    contents = page.frame(name="contents")
    contents.evaluate("__doPostBack('lbtKojiKokoku','')")
    page.wait_for_timeout(1500)
    page.wait_for_load_state("networkidle")

    # ラジオボタンの選択状態を確認
    for rid in ["rbtKokokuDate1Kokoku", "rbtKokokuDate2Kokoku"]:
        checked = page.locator(f"#{rid}").is_checked()
        out.write(f"{rid} checked={checked}\n")
    label_text = page.inner_text("body")
    # 「指定なし」というラベルが近くにあるか確認のため周辺HTMLを見る
    html = page.content()
    idx = html.find("rbtKokokuDate1Kokoku")
    out.write("付近HTML(date1):\n" + html[max(0,idx-300):idx+300] + "\n\n")
    idx2 = html.find("rbtKokokuDate2Kokoku")
    out.write("付近HTML(date2):\n" + html[max(0,idx2-300):idx2+300] + "\n\n")

    # 発注機関 国の機関 -> 防衛省
    page.select_option("#drpTopKikanInf", "0")
    page.wait_for_timeout(1000)
    page.select_option("#drpLargeKikanInf2", "05")
    page.wait_for_timeout(1000)

    # 期間指定なし（1個目のラジオ）を明示的に選択
    page.check("#rbtKokokuDate1Kokoku")

    # 工事の業種は指定しない（広めに：防衛省の全工事を見る）
    page.select_option("#drpCount", "100")
    page.click("#btnSearch")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    page.screenshot(path="spike/screenshots/ippi/05_bouei_nodatefilter.png", full_page=True)
    out.write("結果(防衛省・全工事・期間指定なし):\n")
    out.write(page.inner_text("body")[:3000] + "\n")

    browser.close()

out.close()
