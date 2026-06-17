"""
scrapers/jkk.py

JKK東京（東京都住宅供給公社）電子入札システムの「公表・入札結果」検索画面を
Playwrightで取得する。
対象: 業種=解体（categoryId=015）、案件状態=入札参加受付中（selbidStatus=20）。

アクセス方式:
  1. https://www.to-kousya.or.jp/keiyaku/nyusatu/index.html を開く
  2. 「電子入札公表・結果」リンクをクリック（新タブで e-bid.to-kousya.or.jp が開く。
     直接URLへアクセスすると「不正なアクセスです」になるため、必ずこのリンク経由で開く）
  3. categoryId=解体、selbidStatus=入札参加受付中 を選択して #btnSearch をクリック
  4. 結果テーブル（No./案件状態/案件名/案件区分+入札方式+参加形態/業種/期間/
     申込受付期間/開札予定日時/落札業者名）を解析
  5. 次ページボタン（name="ji_ss_y1"）があれば追従

注: JKKは発注者が常にJKK東京自身のため org_name は固定値。
    案件一覧には公告日に相当する列がないため、申込受付期間の開始日を cft_issue_date、
    終了日を application_deadline とする。bid_deadline は確定しないため空欄。
"""
import re

from . import BidItem

TOP_URL      = "https://www.to-kousya.or.jp/keiyaku/nyusatu/index.html"
CATEGORY_ID  = "015"   # 解体（スパイクで確認）
STATUS_UKETSUKE_CHU = "20"   # 入札参加受付中
ORG_NAME     = "東京都住宅供給公社（JKK東京）"


def _split_lines(cell_text: str) -> list[str]:
    return [s.strip() for s in cell_text.split("\n") if s.strip()]


def _parse_dt(s: str) -> str:
    from datetime import datetime
    s = s.strip()
    for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            pass
    return s


def _parse_period(cell_text: str) -> tuple[str, str]:
    """「2026/04/13 ～ 2026/12/22」「2026/03/02 09:00～2026/03/06 16:00」形式を ISO日付の (開始, 終了) に分割する"""
    parts = re.split(r"[～~]", cell_text.replace("\n", ""))
    if len(parts) != 2:
        return "", ""
    return _parse_dt(parts[0]), _parse_dt(parts[1])


def _parse_results_table(page) -> list[dict]:
    items = []
    rows = page.query_selector_all('a[id^="linkNo_"]')
    for link in rows:
        try:
            auc_id = (link.get_attribute("id") or "").replace("linkNo_", "")
            row = link.evaluate_handle("el => el.closest('tr')").as_element()
            if not row:
                continue
            cells = row.query_selector_all("td")
            if len(cells) < 9:
                continue

            status         = cells[1].inner_text().strip()
            project_name   = cells[2].inner_text().strip()
            kbn_lines      = _split_lines(cells[3].inner_text())
            procedure_type = kbn_lines[1] if len(kbn_lines) > 1 else ""
            entry_type     = kbn_lines[2] if len(kbn_lines) > 2 else ""
            gyoshu         = cells[4].inner_text().strip()
            app_start, app_end = _parse_period(cells[6].inner_text())
            opening_date   = _parse_dt(cells[7].inner_text())

            items.append({
                "key":                  f"jkk_{auc_id}",
                "project_name":         project_name,
                "status":               status,
                "procedure_type":       procedure_type,
                "entry_type":           entry_type,
                "gyoshu":               gyoshu,
                "cft_issue_date":       app_start,
                "application_deadline": app_end,
                "opening_date":         opening_date,
            })
        except Exception as e:
            print(f"  [jkk] 行解析エラー: {e}")
    return items


def fetch(lookback_days: int = 8, headless: bool = True) -> list[BidItem]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[jkk] playwright がインストールされていないためスキップ")
        return []

    print(f"[jkk] 取得開始（業種=解体 案件状態=入札参加受付中）")
    raw_items: list[dict] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx     = browser.new_context(viewport={"width": 1400, "height": 900})
            page    = ctx.new_page()

            page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
            target_link = page.locator("a", has_text="電子入札公表・結果").first
            with ctx.expect_page(timeout=15000) as popup_info:
                target_link.click()
            bid = popup_info.value
            bid.wait_for_load_state("networkidle", timeout=30000)

            bid.select_option('select[name="categoryId"]', CATEGORY_ID)
            bid.select_option('select[name="selbidStatus"]', STATUS_UKETSUKE_CHU)
            bid.locator("input#btnSearch").click()
            bid.wait_for_load_state("networkidle", timeout=30000)
            bid.wait_for_timeout(500)

            page_no = 1
            while True:
                before = len(raw_items)
                raw_items.extend(_parse_results_table(bid))
                print(f"  → ページ{page_no}: {len(raw_items) - before} 件")

                next_btn = bid.locator('[name="ji_ss_y1"]').first
                if next_btn.count() == 0:
                    break
                try:
                    next_btn.click(timeout=3000)
                except Exception:
                    break
                bid.wait_for_load_state("networkidle", timeout=30000)
                bid.wait_for_timeout(300)
                page_no += 1
                if page_no > 20:   # 安全弁（無限ループ防止）
                    break

            browser.close()

    except Exception as e:
        import traceback
        print(f"[jkk] スクレイピングエラー: {e}")
        traceback.print_exc()
        return []

    items: list[BidItem] = [
        BidItem(
            source               = "jkk",
            key                  = r["key"],
            project_name         = r["project_name"],
            org_name             = ORG_NAME,
            pref_name            = "東京都",
            city_name            = "",
            pref_code            = "13",
            gyoshu_codes         = [CATEGORY_ID],
            cft_issue_date       = r["cft_issue_date"],
            procedure_type       = r["procedure_type"],
            doc_uri              = TOP_URL,
            attachments          = [],
            location             = "",
            bid_deadline         = "",
            opening_date         = r["opening_date"],
            application_deadline = r["application_deadline"],
        )
        for r in raw_items
    ]
    print(f"[jkk] 合計 {len(items)} 件")
    return items
