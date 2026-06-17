"""
scrapers/tokyo_metro.py

東京都電子調達システム（都庁本体・入札情報サービス、e-procurement.metro.tokyo.lg.jp）から
「発注予定情報」をPlaywrightで取得する。
対象: 業種=3101（解体工事）。

アクセス方式:
  1. indexPbi.jsp で入札情報サービストップを開く
  2. SelectTargetSubmit(3, 3, '_top') で「発注予定情報」検索画面へ
  3. 「業種の一覧表」リンクをクリックして開く実ポップアップ（window.opener経由で親フォームに反映）で
     その他工事(004)を展開 → 解体工事(3101)を選択 → 追加 → 「選択」で親フォームへ反映しポップアップを閉じる
  4. 「検索」リンクをクリックして結果一覧（table.list-data）を取得
  5. ページネーション（td.areaTitle .pagination 内のリンク）があれば追従

注: 「発注予定情報」は契約締結前の案件一覧であり、入札締切・開札日は未確定のため
    bid_deadline / opening_date は空。希望申請期間の終了日を application_deadline とする。
"""
import re
import time
from datetime import datetime

from . import BidItem

PBI_URL     = "https://www.e-procurement.metro.tokyo.lg.jp/indexPbi.jsp"
GYOSHU_CODE = "3101"   # 解体工事（スパイクで確認。3100は平成29・30年度廃止の旧コード）


def _reiwa_to_year(era_year: int) -> int:
    return 2018 + era_year


def _parse_wareki_date(s: str) -> str:
    """「令和8年6月15日」形式をISO日付に変換する"""
    m = re.search(r"令和(\d+)年(\d+)月(\d+)日", s)
    if not m:
        return s.strip()
    year = _reiwa_to_year(int(m.group(1)))
    return f"{year:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _parse_application_deadline(period: str, base_iso_date: str) -> str:
    """「6月15日 ～6月19日」+ 基準日(公表日)から終了日のISO日付を推定する"""
    m = re.search(r"(\d+)月(\d+)日\s*[～~]\s*(\d+)月(\d+)日", period)
    if not m or not base_iso_date:
        return ""
    base_year = int(base_iso_date[:4])
    start_month = int(m.group(1))
    end_month, end_day = int(m.group(3)), int(m.group(4))
    year = base_year + 1 if end_month < start_month else base_year
    return f"{year:04d}-{end_month:02d}-{end_day:02d}"


def _parse_results_table(page) -> list[dict]:
    items = []
    rows = page.query_selector_all("table.list-data tbody tr")
    for row in rows:
        cells = row.query_selector_all("td")
        if len(cells) < 11:
            continue
        try:
            link = cells[2].query_selector("a")
            if not link:
                continue
            project_name = link.inner_text().strip()
            href = link.get_attribute("href") or ""
            m = re.search(r"SelectSubmitNo\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(\d+)\s*\)", href)
            if not m:
                continue
            cont_no = m.group(1)

            cft_issue_date = _parse_wareki_date(cells[0].inner_text().strip())
            contract_no    = cells[1].inner_text().strip()
            procedure_type = cells[5].inner_text().strip()
            app_period     = cells[8].inner_text().strip()
            org_name       = cells[10].inner_text().strip()

            items.append({
                "key":                  f"tokyometro_{cont_no}",
                "project_name":         project_name,
                "contract_no":          contract_no,
                "org_name":             org_name,
                "cft_issue_date":       cft_issue_date,
                "procedure_type":       procedure_type,
                "application_deadline": _parse_application_deadline(app_period, cft_issue_date),
            })
        except Exception as e:
            print(f"  [tokyo_metro] 行解析エラー: {e}")
    return items


def _select_gyoshu_kaitai(ctx, page) -> bool:
    """「業種の一覧表」ポップアップで解体工事(3101)を選択し、親フォームに反映する"""
    try:
        with ctx.expect_page(timeout=15000) as popup_info:
            page.locator("a", has_text="業種の").first.click()
        popup = popup_info.value
        popup.wait_for_load_state("networkidle", timeout=20000)
        popup.select_option('select[name="preCategory"]', "004")
        popup.evaluate("changeDisp(document.forms[0], 'preCategory')")
        popup.wait_for_timeout(300)
        popup.select_option('select[name="preCategory"]', GYOSHU_CODE)
        popup.locator('input[type="button"][value=" 選択 >> "]').click()
        popup.wait_for_timeout(300)
        popup.locator("a.btnS", has_text="選択").click()
        page.wait_for_timeout(500)
        return True
    except Exception as e:
        print(f"  [tokyo_metro] 業種選択エラー: {e}")
        return False


def fetch(lookback_days: int = 8, headless: bool = True) -> list[BidItem]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[tokyo_metro] playwright がインストールされていないためスキップ")
        return []

    print(f"[tokyo_metro] 取得開始（業種={GYOSHU_CODE} 解体工事）")
    raw_items: list[dict] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx     = browser.new_context(viewport={"width": 1400, "height": 900})
            page    = ctx.new_page()

            page.goto(PBI_URL, wait_until="networkidle", timeout=30000)
            page.evaluate("SelectTargetSubmit(3, 3, '_top')")
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(800)

            if not _select_gyoshu_kaitai(ctx, page):
                browser.close()
                return []

            page.locator("a", has_text="検索").last.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(500)

            count_el = page.query_selector("td.all-page")
            print(f"  → 結果: {count_el.inner_text().strip() if count_el else '(件数不明)'}")

            raw_items.extend(_parse_results_table(page))
            print(f"  → ページ1: {len(raw_items)} 件")

            # ページネーション（次ページへのリンクがあれば追従）
            page_no = 2
            while True:
                next_link = page.locator("td.areaTitle .pagination a", has_text="次").first
                if next_link.count() == 0:
                    break
                next_link.click()
                page.wait_for_load_state("networkidle", timeout=30000)
                before = len(raw_items)
                raw_items.extend(_parse_results_table(page))
                print(f"  → ページ{page_no}: {len(raw_items) - before} 件追加")
                page_no += 1

            browser.close()

    except Exception as e:
        import traceback
        print(f"[tokyo_metro] スクレイピングエラー: {e}")
        traceback.print_exc()
        return []

    items: list[BidItem] = [
        BidItem(
            source               = "tokyometro",
            key                  = r["key"],
            project_name         = r["project_name"],
            org_name             = r["org_name"],
            pref_name            = "東京都",
            city_name            = "",
            pref_code            = "13",
            gyoshu_codes         = [GYOSHU_CODE],
            cft_issue_date       = r["cft_issue_date"],
            procedure_type       = r["procedure_type"],
            doc_uri              = PBI_URL,
            attachments          = [],
            location             = "",
            bid_deadline         = "",
            opening_date         = "",
            application_deadline = r["application_deadline"],
        )
        for r in raw_items
    ]
    print(f"[tokyo_metro] 合計 {len(items)} 件")
    return items
