"""
scrapers/pportal.py

政府電子調達（GEPS）調達ポータル（p-portal.go.jp）から入札公告を取得する。
国の機関（省庁等）のみが対象（都道府県・市区町村は対象外）。

背景: kkj.go.jp（官公需ポータル）は国の機関の案件をp-portal経由で受け取ることが
あるが、その登録が「日付情報を持たない簡易登録」になっているケースがある
（2026-07-18、東京法務局の解体工事案件で発覚）。p-portal自体には公告本文が
PDFではなくHTMLとして直接掲載されており、締切・開札日時等が定型フォーマットで
含まれているため、正規表現でkkjより高い精度で抽出できる。

アクセス方式:
  1. https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115 の検索フォームで
     「公開中の調達案件」を選択し、調達案件名称にキーワードを入力・公開開始日で
     絞り込んで検索（ログイン不要）
  2. 結果一覧の各行「公示本文」リンク（javascript:doSubmitParams(...)）をクリックすると
     同一タブ内で詳細ページ（OAA0104）に遷移する。詳細ページには
     公開開始日・公開終了日・調達機関・調達機関所在地のヘッダー項目と、
     公告内容（本文）がHTMLテキストとしてそのまま含まれる
  3. 本文中の「入札書の提出期限」「開札の日時」「競争参加資格確認申請書の提出期間」を
     正規表現で抽出する（法令様式に基づく定型文言のため安定して拾える）
  4. 「戻る」はブラウザのgo_back()で一覧に復帰する
"""
import re
import time
from datetime import datetime, timedelta

from . import BidItem, PREF_NAME_TO_CODE

SEARCH_URL  = "https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0100?OAA0115"
SEARCH_KEYWORDS: list[str] = ["解体", "除却"]
GYOSHU_KAITAI = "3100"
MAX_ITEMS_PER_KEYWORD = 30   # 安全弁（無限ループ防止）

WAREKI_DATE_RE = re.compile(r"令和\s*0?(\d+)年\s*0?(\d+)月\s*0?(\d+)日")
WAREKI_TIME_RE = re.compile(
    r"令和\s*0?(\d+)年\s*0?(\d+)月\s*0?(\d+)日[^\d]{0,8}?(午前|午後)?\s*0?(\d+)時0?(\d*)分?"
)


def _reiwa_to_year(era_year: int) -> int:
    return 2018 + era_year


def _parse_wareki_date(s: str) -> str:
    """「令和8年7月16日」→"2026-07-16"。時刻情報（午前/午後含む）があれば含めて返す。"""
    if not s:
        return ""
    m = WAREKI_TIME_RE.search(s)
    if m:
        year = _reiwa_to_year(int(m.group(1)))
        month, day = int(m.group(2)), int(m.group(3))
        ampm = m.group(4)
        hour = int(m.group(5))
        minute = int(m.group(6)) if m.group(6) else 0
        if ampm == "午後" and hour != 12:
            hour += 12
        elif ampm == "午前" and hour == 12:
            hour = 0
        try:
            return datetime(year, month, day, hour, minute).isoformat()
        except ValueError:
            pass
    m = WAREKI_DATE_RE.search(s)
    if not m:
        return ""
    year, month, day = _reiwa_to_year(int(m.group(1))), int(m.group(2)), int(m.group(3))
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return ""


def _find_after_label(text: str, *labels: str) -> str:
    """ラベル文言の直後（〜150字程度）から令和日付（時刻含む）を抜き出す。
    「入札、開札の日時及び場所」のような見出しにも同じラベル文言が先に出現するため、
    最後の出現位置（実際の項目欄）を使う"""
    for label in labels:
        positions = [m.start() for m in re.finditer(re.escape(label), text)]
        if not positions:
            continue
        idx = positions[-1]
        snippet = text[idx: idx + 150]
        val = _parse_wareki_date(snippet)
        if val:
            return val
    return ""


def _find_application_deadline(text: str) -> str:
    """「競争参加資格確認申請書の提出期間」等の範囲表記から終了日を抜き出す"""
    idx = text.find("参加資格確認申請書の提出期間")
    if idx == -1:
        idx = text.find("参加資格確認申請書の提出期限")
    if idx == -1:
        return ""
    snippet = text[idx: idx + 200]
    dates = WAREKI_DATE_RE.findall(snippet)
    if len(dates) >= 2:
        year, month, day = dates[1]
        try:
            return datetime(_reiwa_to_year(int(year)), int(month), int(day)).date().isoformat()
        except ValueError:
            return ""
    return _find_after_label(text, "参加資格確認申請書の提出期間", "参加資格確認申請書の提出期限")


def _pref_code_from_location(loc: str) -> str:
    for name, code in PREF_NAME_TO_CODE.items():
        if name in (loc or ""):
            return code
    return ""


def fetch(lookback_days: int = 8, headless: bool = True,
          known_keys: set | None = None) -> list[BidItem]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[pportal] playwright がインストールされていないためスキップ")
        return []
    known_keys = known_keys or set()

    since = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    seen: set[str] = set()
    items: list[BidItem] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
            page = ctx.new_page()

            for kw in SEARCH_KEYWORDS:
                print(f"[pportal] キーワード「{kw}」で検索中...")
                try:
                    page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
                    page.locator("input[name='searchConditionBean.caseDivision'][value='0']").check()
                    page.locator("input[name='searchConditionBean.articleNm']").fill(kw)
                    page.locator("input[name='searchConditionBean.publicStartDateFrom']").fill(since)
                    page.locator("input[name='OAA0102']").click()
                    page.wait_for_load_state("networkidle", timeout=30000)
                    results_url = page.url   # 一覧へ戻る際はgo_back()ではなくこのURLへ再goto（安定）
                except Exception as e:
                    print(f"  [pportal] 検索失敗: {e}")
                    continue

                links = page.locator("a.koukoku")
                count = min(links.count(), MAX_ITEMS_PER_KEYWORD)
                print(f"  → {count} 件")

                for i in range(count):
                    try:
                        links = page.locator("a.koukoku")
                        if i >= links.count():
                            break
                        link = links.nth(i)
                        href = link.get_attribute("href") or ""
                        m = re.search(r"procurementItemInfoId'\s*,\s*value:\s*'(\d+)'", href)
                        item_id = m.group(1) if m else ""

                        link.click()
                        try:
                            page.wait_for_url(re.compile(r"OAA0104"), timeout=15000)
                        except Exception:
                            print(f"    [pportal] index {i} 詳細ページへの遷移タイムアウト")
                            continue
                        page.wait_for_load_state("networkidle", timeout=15000)

                        key = f"pportal_{item_id}" if item_id else ""
                        if not key or key in seen:
                            page.goto(results_url, wait_until="networkidle", timeout=20000)
                            continue
                        seen.add(key)

                        body = page.inner_text("body")

                        def _field(label: str) -> str:
                            fm = re.search(rf"{label}\s*\n?\s*([^\n]+)", body)
                            return fm.group(1).strip() if fm else ""

                        project_name = _field("調達案件名称")
                        org_name     = _field("調達機関")
                        location     = _field("調達機関所在地")
                        public_start = _field("公開開始日")
                        cft_issue_date = _parse_wareki_date(public_start)

                        bid_deadline = _find_after_label(
                            body, "入札書の提出期限", "見積書の提出期限")
                        opening_date = _find_after_label(
                            body, "開札の日時", "開札日時")
                        application_deadline = _find_application_deadline(body)

                        # 「公告内容」に締切等が本文として埋め込まれていない案件は、
                        # 別添の「調達資料」PDFに公告本文が入っている（発注機関が
                        # PDFをアップロードする形式のケース）。ダウンロードリンクを
                        # 添付として保持し、AI抽出（enrich）の材料に使えるようにする
                        attachments = []
                        for a in page.locator("a.text-link").all():
                            try:
                                name = a.inner_text().strip()
                                href = a.get_attribute("href") or ""
                                if "調達資料" in name and href.startswith("http"):
                                    attachments.append({"name": name, "uri": href})
                            except Exception:
                                pass

                        items.append(BidItem(
                            source               = "pportal",
                            key                  = key,
                            project_name         = project_name,
                            org_name             = org_name,
                            pref_name            = location,
                            city_name            = "",
                            pref_code            = _pref_code_from_location(location),
                            gyoshu_codes         = [GYOSHU_KAITAI],
                            cft_issue_date       = cft_issue_date,
                            procedure_type       = "",
                            doc_uri              = page.url,
                            attachments          = attachments,
                            location             = "",
                            bid_deadline         = bid_deadline,
                            opening_date         = opening_date,
                            application_deadline = application_deadline,
                            detail_text          = body[:9000],
                        ))
                        print(f"    取得: {project_name[:30]}")

                        page.goto(results_url, wait_until="networkidle", timeout=20000)
                    except Exception as e:
                        print(f"  [pportal] index {i} 処理エラー: {e}")
                        try:
                            page.goto(results_url, wait_until="networkidle", timeout=20000)
                        except Exception:
                            pass
                time.sleep(0.5)

            browser.close()

    except Exception as e:
        import traceback
        print(f"[pportal] スクレイピングエラー: {e}")
        traceback.print_exc()
        return items

    print(f"[pportal] 合計 {len(items)} 件")
    return items
