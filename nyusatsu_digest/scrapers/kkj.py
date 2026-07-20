"""
scrapers/kkj.py

官公需情報ポータルサイト（kkj.go.jp）APIから入札公告を取得する。
"""
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from . import BidItem, PREF_NAME_TO_CODE

API_URL       = "http://www.kkj.go.jp/api/"
LOOKBACK_DAYS = 8
API_COUNT     = 100

# 件名に含まれるキーワード（OR検索・重複除去して統合）
# 「解体」のみだと「〇〇除却工事」のように件名に「解体」の文字を含まない
# 案件を取りこぼすため追加した（2026-07-18）。「撤去」は通信機器・街路樹・
# 航路標識等の解体と無関係な案件が大半を占めノイズが多いため見送った
# （実測: 撤去24件中、解体工事に該当する案件はほぼ0件）
SEARCH_KEYWORDS: list[str] = ["解体", "除却"]

# 業種コードマップ（キーワード → gyoshu_code）
# キーワードで取得した案件を分類するための参考マップ
KEYWORD_GYOSHU: dict[str, str] = {
    "解体": "3100",
    "撤去": "3100",
    "除却": "3100",
}


def _find_date(text: str, *labels: str) -> str:
    date_pat = re.compile(r'令和\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日')
    lines = text.split('\n')
    for i, line in enumerate(lines):
        for label in labels:
            if re.search(label, line):
                snippet = '\n'.join(lines[i: i + 3])
                m = date_pat.search(snippet)
                if m:
                    return f"令和{m.group(1)}年{m.group(2)}月{m.group(3)}日"
    return ""


def _filter_relevant_names(name: str) -> str:
    """「、」区切りの一括公告から関連案件名のみ残す"""
    RELEVANT_WORDS = set(SEARCH_KEYWORDS) | {"撤去", "除却", "解体"}
    if '、' not in name:
        return name
    parts = [p.strip() for p in name.split('、') if p.strip()]
    matched = [p for p in parts if any(kw in p for kw in RELEVANT_WORDS)]
    return '、'.join(matched) if matched else name


def extract_work_name(raw_name: str, description: str) -> str:
    m = re.search(r'調達案件名称(.{3,80}?)(?:公開開始日|$)', description)
    if m:
        name = m.group(1).strip()
        if len(name) >= 5:
            return _filter_relevant_names(name)
    generic = re.search(r'について$|公告第\d|執行について|^入札公告$', raw_name.strip())
    if not generic:
        return _filter_relevant_names(raw_name)
    for pat in [
        r'工事件名[　\s ]*([^\n（(【「]{4,60})',
        r'工事名[　\s ]+([^\n数量（(【「\d]{4,60}(?:工事|業務|作業|撤去))',
        r'件\s*名[　\s ]+([^\n数量（(【「]{4,60}(?:工事|業務|作業|撤去))',
    ]:
        m = re.search(pat, description)
        if m:
            name = m.group(1).strip().rstrip("　 、。")
            if len(name) >= 5:
                return _filter_relevant_names(name)
    return _filter_relevant_names(raw_name)


def extract_structured(description: str) -> dict:
    d = description
    location = ""
    m = re.search(r'(?:工事場所|履行場所|納入場所)[　\s ]*([^\n（(「]{3,60})', d)
    if m:
        location = m.group(1).strip().rstrip("　 、。")
    bid_deadline = _find_date(d,
        r'入札書.*?提出期限', r'入札締[切め]', r'提出期限', r'入札期限')
    opening_date = _find_date(d, r'開\s*札')
    application_deadline = _find_date(d,
        r'参加申請.*?受付', r'申請受付.*?期限', r'参加資格確認.*?期限',
        r'参加表明.*?締切', r'資格申請.*?締切')
    return {
        "location":             location,
        "bid_deadline":         bid_deadline,
        "opening_date":         opening_date,
        "application_deadline": application_deadline,
    }


def _call_api(project_name: str, since_date: str) -> list[dict]:
    params = {
        "Project_Name":   project_name,
        "CFT_Issue_Date": f"{since_date}/",
        "Count":          str(API_COUNT),
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    print(f"  [kkj] API: {url}")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read().decode("utf-8")
    root = ET.fromstring(data)
    error = root.find("Error")
    if error is not None:
        print(f"  [kkj] APIエラー: {error.text}")
        return []
    raw = []
    for sr in root.findall(".//SearchResult"):
        def get(tag, _sr=sr):
            el = _sr.find(tag)
            return (el.text or "").strip() if el is not None else ""
        attachments = []
        for att in sr.findall(".//Attachment"):
            name_el = att.find("Name")
            uri_el  = att.find("Uri")
            attachments.append({
                "name": (name_el.text or "").strip() if name_el is not None else "",
                "uri":  (uri_el.text  or "").strip() if uri_el  is not None else "",
            })
        raw.append({"get": get, "attachments": attachments})
    return raw


def fetch(lookback_days: int = LOOKBACK_DAYS, known_keys: set | None = None) -> list[BidItem]:
    # known_keys は未使用（kkjは公告PDFが直リンクのため、ダウンロードは enrich 側で行う）
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    seen:  set[str]      = set()
    items: list[BidItem] = []

    for kw in SEARCH_KEYWORDS:
        print(f"[kkj] キーワード「{kw}」で検索中...")
        try:
            raw_list = _call_api(kw, since)
        except Exception as e:
            print(f"  [kkj] 取得エラー: {e}")
            time.sleep(1)
            continue
        print(f"  → {len(raw_list)} 件取得")
        gyoshu = KEYWORD_GYOSHU.get(kw, "")

        for r in raw_list:
            get = r["get"]
            key = get("Key")
            if not key or key in seen:
                continue
            seen.add(key)

            full_desc  = get("ProjectDescription")
            raw_name   = get("ProjectName")
            work_name  = extract_work_name(raw_name, full_desc)
            structured = extract_structured(full_desc)
            api_bid    = get("TenderSubmissionDeadline")
            api_open   = get("OpeningTendersEvent")
            pref_name  = get("PrefectureName")

            items.append(BidItem(
                source               = "kkj",
                key                  = key,
                project_name         = work_name,
                org_name             = get("OrganizationName"),
                pref_name            = pref_name,
                city_name            = get("CityName"),
                pref_code            = PREF_NAME_TO_CODE.get(pref_name, ""),
                gyoshu_codes         = [gyoshu] if gyoshu else [],
                cft_issue_date       = get("CftIssueDate"),
                procedure_type       = get("ProcedureType"),
                doc_uri              = get("ExternalDocumentURI"),
                attachments          = r["attachments"],
                location             = structured["location"],
                bid_deadline         = api_bid or structured["bid_deadline"],
                opening_date         = api_open or structured["opening_date"],
                application_deadline = structured["application_deadline"],
            ))
        time.sleep(0.5)

    items.sort(key=lambda x: x.cft_issue_date, reverse=True)
    print(f"[kkj] 合計 {len(items)} 件")
    return items
