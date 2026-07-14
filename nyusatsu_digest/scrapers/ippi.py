"""
scrapers/ippi.py

入札情報サービス（統合PPI、i-ppi.jp、JACIC運営）から防衛省の解体工事案件を取得する。
kkj.go.jp（官公需情報ポータル）には防衛省の入札情報がほとんど掲載されないため、
このサイトで補完する。

アクセス方式:
  1. https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm を開く（フレームセット）
  2. contents フレーム内で __doPostBack('lbtKojiKokoku','') を実行し、
     工事の「入札公告等を検索」詳細検索画面（Search.aspx?tab=3）に遷移する
  3. 発注機関=国の機関(0)→防衛省(05)、工事の業種=解体工事(29)、
     公告日=期間指定（直近 lookback_days 日）を指定して検索する
  4. 結果テーブル（id=dgrSearchList）の各行を __doPostBack('dgrSearchList','$i') で
     クリックすると、案件概要の詳細ページ（別URL）に遷移する。
     工事場所・公告日時・期限日時・開札日時・添付PDF等を取得後、
     history.back() で検索結果一覧に戻り、次の行を処理する
     （go_back後も一覧の行データが正しく復元されることをスパイクで確認済み）。

注: 防衛省関連の検索には以下の制約がある（JACIC配布の
    「防衛省関係入札情報検索に際してのお願い」より）。これを誤ると
    防衛省の案件が一切検索されない。
    - MAP検索などの簡易検索ではなく、必ず詳細検索を使う
    - 「工事種別」ではなく「工事の業種」のプルダウンで絞り込む
    - 工事場所は指定しない（代表地域しか登録されないため）
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone

from . import BidItem, PREF_NAME_TO_CODE

TOP_URL = "https://www.i-ppi.jp/IPPI/SearchServices/Web/Index.htm"
KIKAN_DAIBUNRUI_KUNI = "0"     # 発注機関 大分類: 国の機関
KIKAN_BOUEISHO       = "05"    # 発注機関 中分類: 防衛省
GYOSYU_KAITAI        = "29"    # 工事の業種: 解体工事
MAX_ITEMS            = 50      # 安全弁（無限ループ防止）

WAREKI_DT_RE = re.compile(r"(\d+)年(\d+)月(\d+)日\s*(\d+)時(\d+)分")


def _parse_dt(s: str) -> str:
    m = WAREKI_DT_RE.search(s or "")
    if not m:
        return ""
    y, mo, d, h, mi = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi).isoformat()


def _split_pref_city(location: str) -> tuple[str, str]:
    for pref in PREF_NAME_TO_CODE:
        if location.startswith(pref):
            return pref, location[len(pref):]
    return "", location


def _make_key(sekkeisyo_no: str, project_name: str, cft_issue_date: str) -> str:
    no = (sekkeisyo_no or "").strip()
    if no:
        return f"ippi_{no}"
    digest = hashlib.sha1(f"{project_name}|{cft_issue_date}".encode("utf-8")).hexdigest()[:16]
    return f"ippi_{digest}"


def _text(page, selector: str) -> str:
    loc = page.locator(selector)
    if loc.count() == 0:
        return ""
    try:
        return loc.first.inner_text().strip()
    except Exception:
        return ""


def _extract_attachments(page) -> list[dict]:
    """公開文書テーブルの行から「公開中」リンクのみを添付として抽出する
    （お問い合わせ先リンクなど他のtr.font_small_clsと区別するため）。"""
    attachments = []
    for row in page.locator("tr.font_small_cls").all():
        cells = row.locator("td").all()
        if len(cells) < 2:
            continue
        try:
            link = cells[1].locator("a")
            if link.count() == 0 or link.first.inner_text().strip() != "公開中":
                continue
            name = cells[0].inner_text().strip()
            href = link.first.get_attribute("href") or ""
            if href.startswith("http"):
                attachments.append({"name": name, "uri": href})
        except Exception:
            continue
    return attachments


def _extract_detail(page) -> dict:
    org_name = _text(page, "#lblHachukikan")
    dept     = _text(page, "#lblHachusha")
    doc_uri  = ""
    if page.locator("#hlkInquiryList").count():
        doc_uri = page.locator("#hlkInquiryList").get_attribute("href") or ""

    return {
        "org_name":       f"{org_name}／{dept}" if dept else org_name,
        "project_name":   _text(page, "#lblKojiNm"),
        "location":       _text(page, "#lblKojiPlaceFrom"),
        "procedure_type": _text(page, "#lblNyusatsuPtn"),
        "sekkeisyo_no":   _text(page, "#lblSekkeisyoNo"),
        "cft_issue_date": _parse_dt(_text(page, "#lblKokokuDate")),
        "bid_deadline":   _parse_dt(_text(page, "#lblkigenDate")),
        "opening_date":   _parse_dt(_text(page, "#lblKasatuDate")),
        "doc_uri":        doc_uri,
        "attachments":    _extract_attachments(page),
    }


def fetch(lookback_days: int = 8, headless: bool = True,
          known_keys: set | None = None) -> list[BidItem]:
    # known_keys は未使用（ippiは添付PDFが直リンクのため、ダウンロードは enrich 側で行う）
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ippi] playwright がインストールされていないためスキップ")
        return []

    print(f"[ippi] 取得開始（発注機関=防衛省 工事の業種=解体工事）")
    raw_items: list[dict] = []

    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx     = browser.new_context(viewport={"width": 1400, "height": 1200})
            page    = ctx.new_page()

            page.goto(TOP_URL, wait_until="networkidle", timeout=30000)
            contents = next(f for f in page.frames if f.name == "contents")
            contents.evaluate("__doPostBack('lbtKojiKokoku','')")
            page.wait_for_timeout(1000)
            page.wait_for_load_state("networkidle")

            page.select_option("#drpTopKikanInf", KIKAN_DAIBUNRUI_KUNI)
            page.wait_for_load_state("networkidle")
            page.select_option("#drpLargeKikanInf2", KIKAN_BOUEISHO)
            page.wait_for_load_state("networkidle")
            page.select_option("#drpKojiGyosyu", GYOSYU_KAITAI)
            page.check("#rbtKokokuDate2Kokoku")
            page.fill("#dateKokokuFromKokoku", since)
            page.fill("#dateKokokuToKokoku", until)
            page.select_option("#drpCount", "100")
            page.click("#btnSearch")
            page.wait_for_timeout(1500)
            page.wait_for_load_state("networkidle")

            body = page.inner_text("body")
            if "見つかりませんでした" in body:
                print("  → 0 件")
                browser.close()
                return []

            count = max(page.locator("#dgrSearchList tr").count() - 1, 0)
            count = min(count, MAX_ITEMS)
            print(f"  → 結果: {count} 件")

            for i in range(count):
                try:
                    page.evaluate(f"__doPostBack('dgrSearchList','${i}')")
                    page.wait_for_timeout(1200)
                    page.wait_for_load_state("networkidle")
                    raw_items.append(_extract_detail(page))
                except Exception as e:
                    print(f"  [ippi] index {i} 解析エラー: {e}")
                finally:
                    try:
                        page.go_back()
                        page.wait_for_timeout(1000)
                        page.wait_for_load_state("networkidle")
                    except Exception as e:
                        print(f"  [ippi] index {i} 「戻る」処理に失敗: {e}")

            browser.close()

    except Exception as e:
        import traceback
        print(f"[ippi] スクレイピングエラー: {e}")
        traceback.print_exc()
        return []

    items: list[BidItem] = []
    for r in raw_items:
        pref_name, city_name = _split_pref_city(r["location"])
        items.append(BidItem(
            source               = "ippi",
            key                  = _make_key(r["sekkeisyo_no"], r["project_name"], r["cft_issue_date"]),
            project_name         = r["project_name"],
            org_name             = r["org_name"],
            pref_name            = pref_name,
            city_name            = city_name,
            pref_code            = PREF_NAME_TO_CODE.get(pref_name, ""),
            gyoshu_codes         = [GYOSYU_KAITAI],
            cft_issue_date       = r["cft_issue_date"],
            procedure_type       = r["procedure_type"],
            doc_uri              = r["doc_uri"],
            attachments          = r["attachments"],
            location             = r["location"],
            bid_deadline         = r["bid_deadline"],
            opening_date         = r["opening_date"],
            application_deadline = "",
        ))
    print(f"[ippi] 合計 {len(items)} 件")
    return items
