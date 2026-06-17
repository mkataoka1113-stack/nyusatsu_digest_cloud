"""
scrapers/chiba.py

ちば電子調達システム（chiba-ep-bis.supercals.jp、千葉県内の県・市町村共同運営）の
「入札予定(公告)」をPlaywrightで取得する。
対象: 調達区分=工事、工事種別=解体工事（コード0010290）、発注機関は全団体（千葉県・全市町村）。

アクセス方式:
  1. https://www.chiba-ep-bis.supercals.jp/ebidPPIPublish/EjPPIj を開く（フレームセット）
  2. menu_Frm内の「入札予定(公告)」リンクをクリック → mainfrm内に cond/list の
     サブフレームセットが表示される
  3. cond フレームの検索フォーム(name="frm")に ChoutatsuCD=00(工事)・
     KoujiSyubetu=0010290(解体工事) をJSで直接セットして送信（select_optionは非表示行のため使えない）
  4. list フレームの各行「表示」リンク(openYotei(index))をクリックすると、
     mainfrmが詳細1ページ（公告日・締切・開札日時等の詳細）に置き換わる
  5. 詳細ページの「戻る」(document.nextfrm.submit()) でlist一覧に復帰し、次の行を処理する

注: 検索結果一覧には行ごとの一意ID表示がなく(openYotei(index)はその場の表示順インデックス)、
    安定したキーが取得できないため、発注機関+案件名+公告日からハッシュ値を作ってキーとする。
"""
import hashlib
import re
import time
from datetime import datetime

from . import BidItem

ENTRY_URL   = "https://www.chiba-ep-bis.supercals.jp/ebidPPIPublish/EjPPIj"
CHOUTATSU_KOUJI = "00"        # 調達区分: 工事
KOUJI_SYUBETU_KAITAI = "0010290"   # 工事種別: 解体工事（スパイクで確認）
MAX_ITEMS   = 50   # 安全弁（無限ループ防止）

WAREKI_RE = re.compile(
    r"令和\s*0?(\d+)[-年](\d+)[-月](\d+)日?(?:\s+(\d+):(\d+)\s*(AM|PM))?"
)


def _reiwa_to_year(era_year: int) -> int:
    return 2018 + era_year


def _parse_wareki(s: str) -> str:
    if not s:
        return ""
    m = WAREKI_RE.search(s)
    if not m:
        return ""
    year = _reiwa_to_year(int(m.group(1)))
    month, day = int(m.group(2)), int(m.group(3))
    if m.group(4) is None:
        return f"{year:04d}-{month:02d}-{day:02d}"
    hour, minute, ampm = int(m.group(4)), int(m.group(5)), m.group(6)
    if ampm == "PM" and hour != 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    return datetime(year, month, day, hour, minute).isoformat()


def _parse_range_end(s: str) -> str:
    if not s:
        return ""
    parts = re.split(r"\s*[～~]\s*", s)
    return _parse_wareki(parts[-1]) if parts else ""


def _extract_city_name(location: str) -> str:
    m = re.match(r"^(.+?[市町村])", location or "")
    return m.group(1) if m else ""


def _make_key(org_name: str, project_name: str, kokuho_date: str) -> str:
    raw = f"{org_name}|{project_name}|{kokuho_date}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"chiba_{digest}"


def _wait_for_main_frame_with(page, predicate_js: str, timeout_sec: int = 15):
    """mainfrm に predicate_js (boolean式) が真になるまでポーリングして返す"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        frame = next((f for f in page.frames if f.name == "mainfrm"), None)
        if frame:
            try:
                if frame.evaluate(predicate_js):
                    return frame
            except Exception:
                pass
        time.sleep(0.3)
    return None


def _extract_detail(frame) -> dict:
    return frame.evaluate("""() => {
        const result = {};
        document.querySelectorAll('td.INPUT_TITLE_L_L').forEach(td => {
            const label = td.innerText.trim();
            const val = td.nextElementSibling ? td.nextElementSibling.innerText.trim() : '';
            if (label) result[label] = val;
        });
        return result;
    }""")


def fetch(lookback_days: int = 8, headless: bool = True) -> list[BidItem]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[chiba] playwright がインストールされていないためスキップ")
        return []

    print(f"[chiba] 取得開始（調達区分=工事 工事種別=解体工事）")
    raw_items: list[dict] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx     = browser.new_context(viewport={"width": 1400, "height": 1200})
            page    = ctx.new_page()

            page.goto(ENTRY_URL, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(1500)

            menu = next(f for f in page.frames if f.name == "menu_Frm")
            menu.locator("a", has_text="入札予定(公告)").first.click()
            page.wait_for_timeout(2000)

            cond = next(f for f in page.frames if f.name == "cond")
            cond.evaluate(f"""() => {{
                document.frm.ChoutatsuCD.value = '{CHOUTATSU_KOUJI}';
                document.frm.KoujiSyubetu.value = '{KOUJI_SYUBETU_KAITAI}';
                document.frm.ejMaxDisplayRowCount.value = '100';
                document.frm.submit();
            }}""")
            page.wait_for_timeout(3000)

            lst = next(f for f in page.frames if f.name == "list")
            count = lst.locator('a[onclick*="openYotei"]').count()
            count = min(count, MAX_ITEMS)
            print(f"  → 結果: {count} 件")

            for i in range(count):
                lst = next(f for f in page.frames if f.name == "list")
                try:
                    lst.locator('a[onclick*="openYotei"]').nth(i).click()
                    main_frame = _wait_for_main_frame_with(
                        page, "() => !!document.querySelector('td.INPUT_TITLE_L_L')"
                    )
                    if main_frame is None:
                        print(f"  [chiba] index {i} 詳細画面の読み込みタイムアウト")
                    else:
                        data = _extract_detail(main_frame)

                        org_name     = data.get("入札担当部署", "")
                        project_name = data.get("案件名", "")
                        location     = data.get("工事／納入場所", "")
                        kokuho_date  = _parse_wareki(data.get("公告日", ""))

                        raw_items.append({
                            "key":                  _make_key(org_name, project_name, data.get("公告日", "")),
                            "project_name":         project_name,
                            "org_name":             org_name,
                            "location":             location,
                            "city_name":            _extract_city_name(location),
                            "cft_issue_date":       kokuho_date,
                            "procedure_type":       data.get("入札方式", ""),
                            "bid_deadline":         _parse_wareki(data.get("入札締切予定日時", "")),
                            "opening_date":         _parse_wareki(data.get("開札予定日時", "")),
                            "application_deadline": _parse_range_end(data.get("参加申請書受付日時", "")),
                        })
                except Exception as e:
                    print(f"  [chiba] index {i} 解析エラー: {e}")
                finally:
                    # 戻る（リスト復帰）。これを必ず実行しないと次のインデックス処理が壊れる
                    try:
                        page.evaluate("top.mainfrm.document.nextfrm.submit()")
                    except Exception as e:
                        print(f"  [chiba] index {i} 「戻る」処理に失敗: {e}")
                    page.wait_for_timeout(1200)

            browser.close()

    except Exception as e:
        import traceback
        print(f"[chiba] スクレイピングエラー: {e}")
        traceback.print_exc()
        return []

    items: list[BidItem] = [
        BidItem(
            source               = "chiba",
            key                  = r["key"],
            project_name         = r["project_name"],
            org_name             = r["org_name"],
            pref_name            = "千葉県",
            city_name            = r["city_name"],
            pref_code            = "12",
            gyoshu_codes         = [KOUJI_SYUBETU_KAITAI],
            cft_issue_date       = r["cft_issue_date"],
            procedure_type       = r["procedure_type"],
            doc_uri              = ENTRY_URL,
            attachments          = [],
            location             = r["location"],
            bid_deadline          = r["bid_deadline"],
            opening_date         = r["opening_date"],
            application_deadline = r["application_deadline"],
        )
        for r in raw_items
    ]
    print(f"[chiba] 合計 {len(items)} 件")
    return items
