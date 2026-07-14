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

詳細取得: 詳細ページには非表示の downloadForm があり、AddInfoURL01〜10 に添付ファイル名、
    downloadStart(idx) でダウンロードできる（スパイク82で確認）。未通知（known_keys にない）
    案件のみ「公告」を含む添付（zip または PDF）を1件ダウンロードし、テキスト化して
    detail_text に格納する（詳細ページ本文と連結）。
"""
import hashlib
import io
import re
import time
import zipfile
from datetime import datetime

from . import BidItem

ENTRY_URL   = "https://www.chiba-ep-bis.supercals.jp/ebidPPIPublish/EjPPIj"
CHOUTATSU_KOUJI = "00"        # 調達区分: 工事
KOUJI_SYUBETU_KAITAI = "0010290"   # 工事種別: 解体工事（スパイクで確認）
MAX_ITEMS   = 50   # 安全弁（無限ループ防止）
MAX_DETAILS = 15   # 1回の実行で公告ファイルをダウンロードする上限（安全弁）

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


def _wait_for_list_frame(page, timeout_sec: int = 10):
    # 「戻る」での復帰は不安定（体感5割で失敗）だが、_restore_list による検索やり直しが
    # 確実に機能するため、待ちすぎず早めに諦めてリカバリに移る
    """list フレームが openYotei リンクを持つ状態になるまでポーリングして返す"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        frame = next((f for f in page.frames if f.name == "list"), None)
        if frame:
            try:
                if frame.locator('a[onclick*="openYotei"]').count() > 0:
                    return frame
            except Exception:
                pass
        time.sleep(0.5)
    return None


def _restore_list(page) -> object | None:
    """「戻る」での一覧復帰に失敗したとき、メニューから検索をやり直して一覧を復元する"""
    try:
        menu = next((f for f in page.frames if f.name == "menu_Frm"), None)
        if menu is None:
            return None
        menu.locator("a", has_text="入札予定(公告)").first.click()
        page.wait_for_timeout(2000)
        cond = next((f for f in page.frames if f.name == "cond"), None)
        if cond is None:
            return None
        cond.evaluate(f"""() => {{
            document.frm.ChoutatsuCD.value = '{CHOUTATSU_KOUJI}';
            document.frm.KoujiSyubetu.value = '{KOUJI_SYUBETU_KAITAI}';
            document.frm.ejMaxDisplayRowCount.value = '100';
            document.frm.submit();
        }}""")
        page.wait_for_timeout(3000)
        return _wait_for_list_frame(page)
    except Exception as e:
        print(f"  [chiba] 一覧の復元に失敗: {e}")
        return None


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


def _pdf_to_text(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception as e:
        print(f"  [chiba] PDFテキスト抽出失敗: {e}")
        return ""


def _download_kokoku(page, frame) -> tuple[str, list]:
    """詳細ページの downloadForm から「公告」を含む添付を1件ダウンロードし、
    (テキスト, 公告PDFファイル[{"name","data"}]) を返す"""
    files = frame.evaluate("""() => {
        const out = [];
        if (!document.downloadForm) return out;
        for (let i = 1; i <= 10; i++) {
            const el = document.downloadForm['AddInfoURL' + String(i).padStart(2, '0')];
            if (el && el.value) out.push({idx: i, name: el.value});
        }
        return out;
    }""")
    target = next((f for f in files if "公告" in f["name"]), None)
    if not target:
        return "", []
    with page.expect_download(timeout=30000) as dl_info:
        frame.evaluate(f"downloadStart({target['idx']})")
    dl = dl_info.value
    with open(dl.path(), "rb") as fh:
        data = fh.read()

    name = target["name"].lower()
    if name.endswith(".pdf"):
        return _pdf_to_text(data), [{"name": target["name"], "data": data}]
    if name.endswith(".zip"):
        texts = []
        kokoku_files = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            for n in zf.namelist():
                if n.lower().endswith(".pdf"):
                    pdf_data = zf.read(n)
                    texts.append(_pdf_to_text(pdf_data))
                    kokoku_files.append({"name": n.rsplit("/", 1)[-1], "data": pdf_data})
                if len(texts) >= 3:   # 個別編・共通編など複数PDFまで
                    break
        except Exception as e:
            print(f"  [chiba] zip展開失敗: {e}")
        return "\n\n".join(t for t in texts if t), kokoku_files
    return "", []


def fetch(lookback_days: int = 8, headless: bool = True,
          known_keys: set | None = None) -> list[BidItem]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[chiba] playwright がインストールされていないためスキップ")
        return []
    known_keys = known_keys or set()

    print(f"[chiba] 取得開始（調達区分=工事 工事種別=解体工事）")
    raw_items: list[dict] = []
    detail_count = 0

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx     = browser.new_context(viewport={"width": 1400, "height": 1200},
                                          accept_downloads=True)
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

            lst = _wait_for_list_frame(page)
            if lst is None:
                print("  [chiba] 検索結果一覧が読み込まれませんでした")
                browser.close()
                return []
            count = lst.locator('a[onclick*="openYotei"]').count()
            count = min(count, MAX_ITEMS)
            print(f"  → 結果: {count} 件")

            for i in range(count):
                lst = _wait_for_list_frame(page)
                if lst is None:
                    print(f"  [chiba] index {i} 一覧フレームの復帰タイムアウト → 検索やり直しで復元")
                    lst = _restore_list(page)
                if lst is None:
                    print(f"  [chiba] index {i} 一覧を復元できず中断")
                    break
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
                        key          = _make_key(org_name, project_name, data.get("公告日", ""))

                        # 詳細ページの全ラベルをテキスト化（予定価格・工期などを含む）
                        detail_text = "\n".join(f"{k}\t{v}" for k, v in data.items() if v)

                        # 未通知案件のみ公告ファイル（zip/PDF）をダウンロードしてテキスト追加
                        kokoku_files = []
                        if key not in known_keys and detail_count < MAX_DETAILS:
                            try:
                                kokoku_text, kokoku_files = _download_kokoku(page, main_frame)
                                if kokoku_text:
                                    detail_text += "\n\n=== 入札公告 ===\n" + kokoku_text
                                    detail_count += 1
                                    print(f"    公告取得OK: {project_name[:25]}"
                                          f"（{len(kokoku_text)}字・PDF{len(kokoku_files)}件）")
                            except Exception as e:
                                print(f"    [chiba] 公告ダウンロード失敗（{project_name[:20]}）: {e}")

                        raw_items.append({
                            "key":                  key,
                            "project_name":         project_name,
                            "org_name":             org_name,
                            "location":             location,
                            "city_name":            _extract_city_name(location),
                            "cft_issue_date":       kokuho_date,
                            "procedure_type":       data.get("入札方式", ""),
                            "bid_deadline":         _parse_wareki(data.get("入札締切予定日時", "")),
                            "opening_date":         _parse_wareki(data.get("開札予定日時", "")),
                            "application_deadline": _parse_range_end(data.get("参加申請書受付日時", "")),
                            "detail_text":          detail_text,
                            "kokoku_files":         kokoku_files,
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
            detail_text          = r.get("detail_text", ""),
            kokoku_files         = r.get("kokoku_files", []),
        )
        for r in raw_items
    ]
    print(f"[chiba] 合計 {len(items)} 件")
    return items
