"""
scrapers/etokyo.py

東京都電子調達サービス（e-tokyo.lg.jp）から入札公告をPlaywrightで取得する。
対象: 発注案件情報（工事）、業種=3100（解体工事）、全自治体。

アクセス方式:
  1. フレームセット URL に GET でアクセス（FrmLeft + FrmMain が読み込まれる）
  2. メインページから JS で FrmMain に P002 フォームを POST 送信
  3. FrmMain フレームで業種コード・日付をセットし、フォームサブミット
  4. 結果ページを解析（table.list-table > tr.list-line）
"""
import re
import time
from datetime import datetime, timedelta

from . import BidItem

FRAMESET_URL  = "https://www.e-tokyo.lg.jp/choutatu_ppij/ppij/pub"
SYSTEM_URL    = "https://www.e-tokyo.lg.jp/choutatu_ppij/cmn/tmg/cmn/jsp/indexQ.jsp"
LOOKBACK_DAYS = 8

GYOSHU_CODE   = "3100"   # 解体工事（スパイクで確認）


def _parse_dt(dt_str: str) -> str:
    for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(dt_str.strip(), fmt).isoformat()
        except ValueError:
            pass
    return dt_str.strip()


def _parse_results_frame(frame) -> list[dict]:
    items = []
    rows = frame.query_selector_all("table.list-table tbody tr")
    for row in rows:
        try:
            link = row.query_selector("td.list-data-akname a")
            if not link:
                continue
            project_name = link.inner_text().strip()
            href         = link.get_attribute("href") or ""
            m = re.search(r"listSubmit\('P002','7','([^']+)'", href)
            if not m:
                continue
            key = f"etokyo_{m.group(1)}"

            cells = row.query_selector_all("td.list-data")

            def cell(idx):
                return cells[idx].inner_text().strip() if idx < len(cells) else ""

            city_name      = cell(0)
            cft_issue_date = _parse_dt(cell(2))
            bid_deadline   = _parse_dt(cell(3))
            opening_date   = _parse_dt(cell(4))
            proc_raw       = cell(5)
            proc_map       = {"一般": "一般競争入札", "希望": "希望型指名競争", "指名": "指名競争入札"}
            procedure_type = proc_map.get(proc_raw, proc_raw)
            app_period     = cell(6)
            app_deadline   = _parse_dt(app_period.split("～")[-1]) if "～" in app_period else ""

            items.append({
                "key":                  key,
                "project_name":         project_name,
                "city_name":            city_name,
                "cft_issue_date":       cft_issue_date,
                "bid_deadline":         bid_deadline,
                "opening_date":         opening_date,
                "procedure_type":       procedure_type,
                "application_deadline": app_deadline,
            })
        except Exception as e:
            print(f"  [etokyo] 行解析エラー: {e}")
    return items


def _get_page_count(frame) -> int:
    try:
        el = frame.query_selector("td.list-count-disp")
        if el:
            m = re.search(r'(\d+)/(\d+)', el.inner_text())
            if m:
                return int(m.group(2))
    except Exception:
        pass
    return 1


def _wait_for_frame_form(page, frame_name: str, selector: str, timeout_sec: int = 20) -> object | None:
    """指定フレームに selector が現れるまでポーリングして返す"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        frame = next((f for f in page.frames if f.name == frame_name), None)
        if frame:
            el = frame.query_selector(selector)
            if el:
                return frame
        time.sleep(0.5)
    return None


def fetch(lookback_days: int = LOOKBACK_DAYS, headless: bool = True) -> list[BidItem]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[etokyo] playwright がインストールされていないためスキップ")
        return []

    today     = datetime.now()
    since     = today - timedelta(days=lookback_days)
    date_to   = today.strftime("%Y%m%d")
    date_from = since.strftime("%Y%m%d")
    print(f"[etokyo] 取得開始（{date_from}〜{date_to}、業種={GYOSHU_CODE}）")

    raw_items: list[dict] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx     = browser.new_context(viewport={"width": 1400, "height": 900})
            page    = ctx.new_page()

            # Step1: フレームセットを読み込む（FrmLeft + FrmMain が生成される）
            page.goto(FRAMESET_URL, wait_until="networkidle", timeout=30000)

            # Step2: メインページ JS から FrmMain に P002 フォームをPOST送信
            page.evaluate("""() => {
                const f = document.createElement('form');
                f.method = 'post';
                f.action = 'pub';
                f.target = 'FrmMain';
                const add = (n, v) => {
                    const i = document.createElement('input');
                    i.type = 'hidden'; i.name = n; i.value = v;
                    f.appendChild(i);
                };
                add('s', 'P002');
                add('a', '1');
                document.body.appendChild(f);
                f.submit();
            }""")

            # Step3: FrmMain に P002 フォームが読み込まれるまで待機
            main_frame = _wait_for_frame_form(page, "FrmMain", 'select[name="year"]', timeout_sec=20)
            if not main_frame:
                print("[etokyo] P002フォームが FrmMain に読み込まれませんでした")
                browser.close()
                return []
            print(f"  FrmMain フォーム確認 OK (url={main_frame.url[:80]})")

            # Step4: フォームに値をセット（querySelectorで確実にアクセス）
            # 全自治体チェック
            main_frame.evaluate("""() => {
                document.querySelectorAll('input[name="govCode"]')
                    .forEach(cb => cb.checked = true);
            }""")

            # 年度
            main_frame.select_option('select[name="year"]', str(today.year))

            # 業種コード（スパイクで確認済みの4フィールド）
            main_frame.evaluate(f"""() => {{
                const set = (name, val) => {{
                    const el = document.querySelector('[name="' + name + '"]');
                    if (el) el.value = val;
                }};
                set('categoryCode', '{GYOSHU_CODE}');
                set('constKbnCd',   '{GYOSHU_CODE}');
                set('selectConst',  '{GYOSHU_CODE} 解体工事');
                set('TextgyosyuCd', ' 解体工事');
            }}""")

            # 公表期間
            main_frame.fill('input[name="pubStDate"]', date_from)
            main_frame.fill('input[name="pubEndDate"]', date_to)

            # Step5: FrmMain 内でフォームをサブミット（target=_self で FrmMain 内に結果を表示）
            main_frame.evaluate("""() => {
                const f = document.forms['main'] || document.querySelector('form');
                if (!f) return;
                f.target = '_self';
                const setHidden = (name, val) => {
                    let el = f.querySelector('[name="' + name + '"]');
                    if (!el) {
                        el = document.createElement('input');
                        el.type = 'hidden'; el.name = name;
                        f.appendChild(el);
                    }
                    el.value = val;
                };
                setHidden('s', 'P002');
                setHidden('a', '3');
                f.submit();
            }""")

            # 結果が読み込まれるまで待機
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(0.5)
            main_frame = next((f for f in page.frames if f.name == "FrmMain"), None)
            if not main_frame:
                print("[etokyo] 結果フレームが見つかりません")
                browser.close()
                return []

            count_el = main_frame.query_selector("td.list-count-disp")
            count_txt = count_el.inner_text().strip() if count_el else "(件数不明)"
            print(f"  → 結果: {count_txt}")

            total_pages = _get_page_count(main_frame)
            raw_items.extend(_parse_results_frame(main_frame))
            print(f"  → ページ1: {len(raw_items)} 件")

            # ページネーション
            for page_no in range(2, total_pages + 1):
                next_link = main_frame.query_selector("a:has-text('次へ')")
                if not next_link:
                    break
                next_link.click()
                page.wait_for_load_state("networkidle")
                main_frame = next((f for f in page.frames if f.name == "FrmMain"), main_frame)
                before = len(raw_items)
                raw_items.extend(_parse_results_frame(main_frame))
                print(f"  → ページ{page_no}: {len(raw_items) - before} 件追加")

            browser.close()

    except Exception as e:
        import traceback
        print(f"[etokyo] スクレイピングエラー: {e}")
        traceback.print_exc()
        return []

    items: list[BidItem] = [
        BidItem(
            source               = "etokyo",
            key                  = r["key"],
            project_name         = r["project_name"],
            org_name             = r["city_name"],
            pref_name            = "東京都",
            city_name            = r["city_name"],
            pref_code            = "13",
            gyoshu_codes         = [GYOSHU_CODE],
            cft_issue_date       = r["cft_issue_date"],
            procedure_type       = r["procedure_type"],
            doc_uri              = SYSTEM_URL,
            attachments          = [],
            location             = "",
            bid_deadline         = r["bid_deadline"],
            opening_date         = r["opening_date"],
            application_deadline = r["application_deadline"],
        )
        for r in raw_items
    ]
    print(f"[etokyo] 合計 {len(items)} 件")
    return items
