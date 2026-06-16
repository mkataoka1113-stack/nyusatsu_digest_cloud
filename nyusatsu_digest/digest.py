"""
nyusatsu_digest/digest.py

官公需情報ポータルサイト API (kkj.go.jp) から「解体」関連の新着入札公告を取得し、
未送信のものだけをメールで配信 + GitHub Pages用ダッシュボードHTMLを生成する。
GitHub Actions から毎日 1 回（JST 朝）実行する。

使い方:
  python nyusatsu_digest/digest.py
"""
import json
import os
import re
import smtplib
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH   = os.path.join(BASE_DIR, "config.json")
SENT_IDS_PATH = os.path.join(BASE_DIR, "sent_ids.json")
DOCS_DIR      = os.path.join(os.path.dirname(BASE_DIR), "docs")
API_URL       = "http://www.kkj.go.jp/api/"

LOOKBACK_DAYS          = 8    # API取得対象（直近N日間）
SENT_ID_RETENTION_DAYS = 30   # 送信済みID保持期間（ダッシュボード表示も兼ねる）
API_COUNT              = 100  # 1回のAPI呼び出し最大件数

# ── 検索条件 ──────────────────────────────────────────────────────────
# 件名に含まれるキーワード（複数指定時はOR検索・重複除去して統合）
SEARCH_KEYWORDS: list[str] = ["解体"]

# 都道府県コードで絞り込む場合に指定（空リスト=全国）
# 例: ["13"] で東京都のみ、["13", "14"] で東京都＋神奈川県
FILTER_LG_CODES: list[str] = []

# カテゴリで絞り込む場合に指定（空文字=全て）
# "1"=物品  "2"=工事  "3"=役務
FILTER_CATEGORY: str = ""


# ---------------------------------------------------------------------------
# 設定ファイル / 送信済みID
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if all(k in os.environ for k in ("GMAIL_FROM", "GMAIL_APP_PASSWORD", "GMAIL_TO")):
        return {
            "gmail": {
                "from": os.environ["GMAIL_FROM"],
                "to": os.environ["GMAIL_TO"],
                "app_password": os.environ["GMAIL_APP_PASSWORD"],
            }
        }
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_sent_ids() -> dict:
    if not os.path.exists(SENT_IDS_PATH):
        return {}
    with open(SENT_IDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_sent_ids(sent_ids: dict) -> None:
    with open(SENT_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(sent_ids, f, ensure_ascii=False, indent=2)


def prune_sent_ids(sent_ids: dict) -> dict:
    threshold = datetime.now(timezone.utc) - timedelta(days=SENT_ID_RETENTION_DAYS)
    pruned = {}
    for key, entry in sent_ids.items():
        try:
            dt = datetime.fromisoformat(entry["cft_issue_date"].replace("Z", "+00:00"))
            if dt >= threshold:
                pruned[key] = entry
        except (KeyError, ValueError):
            pass
    return pruned


# ---------------------------------------------------------------------------
# 公告文からの構造化抽出
# ---------------------------------------------------------------------------

def _find_date(text: str, *labels: str) -> str:
    """ラベルキーワードの近くにある「令和X年X月X日」を探す"""
    for label in labels:
        m = re.search(
            label + r".{0,80}令和\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日",
            text, re.DOTALL
        )
        if m:
            return f"令和{m.group(1)}年{m.group(2)}月{m.group(3)}日"
    return ""


def extract_work_name(raw_name: str, description: str) -> str:
    """
    ProjectName が汎用タイトル（「〜について」「公告第〜」など）の場合、
    公告文から正式な工事名を抽出して返す。
    p-portal 形式（調達案件名称〜）にも対応。
    """
    # p-portal 形式：調達案件名称フィールドを優先
    m = re.search(r'調達案件名称(.{3,80}?)(?:公開開始日|$)', description)
    if m:
        name = m.group(1).strip()
        if len(name) >= 5:
            return name

    # 汎用タイトルかどうか判定
    generic = re.search(r'について$|公告第\d|執行について|^入札公告$', raw_name.strip())
    if not generic:
        return raw_name  # そのままでOK

    # 公告文から工事名を探す
    for pat in [
        r'工事件名[　\s ]*([^\n（(【「]{4,60})',
        r'工事名[　\s ]+([^\n数量（(【「\d]{4,60}(?:工事|業務|作業|撤去))',
        r'件\s*名[　\s ]+([^\n数量（(【「]{4,60}(?:工事|業務|作業|撤去))',
    ]:
        m = re.search(pat, description)
        if m:
            name = m.group(1).strip().rstrip("　 、。")
            if len(name) >= 5:
                return name

    return raw_name


def extract_structured(description: str) -> dict:
    """
    公告文全文から構造化情報（工事場所・日付類）を抽出する。
    抽出できない項目は空文字。
    """
    d = description

    # 工事場所
    location = ""
    m = re.search(r'(?:工事場所|履行場所|納入場所)[　\s ]*([^\n（(「]{3,60})', d)
    if m:
        location = m.group(1).strip().rstrip("　 、。")

    # 入札締切（入札書提出期限）
    bid_deadline = _find_date(d,
        r'入札書.*?提出期限', r'入札締[切め]', r'提出期限', r'入札期限')

    # 開札日
    opening_date = _find_date(d, r'開\s*札')

    # 参加申請受付締切（希望型・制限付き競争入札で登場）
    application_deadline = _find_date(d,
        r'参加申請.*?受付', r'申請受付.*?期限', r'参加資格確認.*?期限',
        r'参加表明.*?締切', r'資格申請.*?締切')

    return {
        "location":             location,
        "bid_deadline":         bid_deadline,
        "opening_date":         opening_date,
        "application_deadline": application_deadline,
    }


# ---------------------------------------------------------------------------
# API 呼び出し
# ---------------------------------------------------------------------------

def call_api(project_name: str, since_date: str) -> list[dict]:
    params: dict = {
        "Project_Name":   project_name,
        "CFT_Issue_Date": f"{since_date}/",
        "Count":          str(API_COUNT),
    }
    if FILTER_LG_CODES:
        params["LG_Code"] = ",".join(FILTER_LG_CODES)
    if FILTER_CATEGORY:
        params["Category"] = FILTER_CATEGORY

    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    print(f"  API: {url}")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read().decode("utf-8")

    root = ET.fromstring(data)
    error = root.find("Error")
    if error is not None:
        print(f"  APIエラー: {error.text}")
        return []

    results = []
    for sr in root.findall(".//SearchResult"):
        def get(tag):
            el = sr.find(tag)
            return (el.text or "").strip() if el is not None else ""

        attachments = []
        for att in sr.findall(".//Attachment"):
            name_el = att.find("Name")
            uri_el  = att.find("Uri")
            attachments.append({
                "name": (name_el.text or "").strip() if name_el is not None else "",
                "uri":  (uri_el.text  or "").strip() if uri_el  is not None else "",
            })

        full_desc    = get("ProjectDescription")
        raw_name     = get("ProjectName")
        work_name    = extract_work_name(raw_name, full_desc)
        structured   = extract_structured(full_desc)

        results.append({
            "key":                  get("Key"),
            "project_name":         work_name,            # 正式工事名（抽出済み）
            "org_name":             get("OrganizationName"),
            "pref_name":            get("PrefectureName"),
            "city_name":            get("CityName"),
            "cft_issue_date":       get("CftIssueDate"),
            "category":             get("Category"),
            "procedure_type":       get("ProcedureType"),
            "doc_uri":              get("ExternalDocumentURI"),
            "tender_deadline":      get("TenderSubmissionDeadline"),
            "opening_event":        get("OpeningTendersEvent"),
            "period_end":           get("PeriodEndTime"),
            "attachments":          attachments,
            # 公告文から抽出した構造化情報
            "location":             structured["location"],
            "bid_deadline":         structured["bid_deadline"],
            "opening_date":         structured["opening_date"],
            "application_deadline": structured["application_deadline"],
        })
    return results


def fetch_new_items() -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    seen:  set[str]  = set()
    items: list[dict] = []

    for kw in SEARCH_KEYWORDS:
        print(f"キーワード「{kw}」で検索中...")
        fetched = call_api(kw, since)
        print(f"  → {len(fetched)} 件取得")
        for item in fetched:
            key = item["key"]
            if key and key not in seen:
                seen.add(key)
                items.append(item)
        time.sleep(0.5)

    items.sort(key=lambda x: x["cft_issue_date"], reverse=True)
    return items


# ---------------------------------------------------------------------------
# 書式ヘルパー
# ---------------------------------------------------------------------------

def fmt_date(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日")
    except ValueError:
        return iso_str or "—"


def fmt_jp_date(jp_str: str) -> str:
    """「令和X年X月X日」そのまま返す（空なら—）"""
    return jp_str if jp_str else "—"


# ---------------------------------------------------------------------------
# メール
# ---------------------------------------------------------------------------

def build_card_email(item: dict) -> str:
    font = "'Yu Gothic','Yu Gothic UI',sans-serif"
    org  = item.get("org_name") or "—"
    area = "".join(filter(None, [item.get("pref_name"), item.get("city_name")])) or "—"
    date = fmt_date(item.get("cft_issue_date", ""))
    category   = item.get("category") or "—"
    procedure  = item.get("procedure_type") or "—"
    location   = item.get("location") or "—"
    bid_dl     = fmt_jp_date(item.get("bid_deadline", ""))
    opening    = fmt_jp_date(item.get("opening_date", ""))
    app_dl     = fmt_jp_date(item.get("application_deadline", ""))
    uri        = item.get("doc_uri") or ""

    link_html = (
        f'<p style="margin:8px 0 0;font-family:{font};">'
        f'<a href="{uri}" style="color:#2980b9;font-size:13px;">公告元ページを見る →</a></p>'
        if uri else ""
    )
    att_links = " / ".join(
        f'<a href="{a["uri"]}" style="color:#2980b9;">{a["name"] or "添付ファイル"}</a>'
        for a in (item.get("attachments") or []) if a.get("uri")
    )
    att_html = (
        f'<p style="margin:4px 0;font-size:12px;color:#555;font-family:{font};">'
        f'添付: {att_links}</p>'
        if att_links else ""
    )

    rows = [
        ("発注機関",   org),
        ("所在地",     area),
        ("公告日",     date),
        ("カテゴリ",   category),
        ("入札方式",   procedure),
        ("工事場所",   location),
        ("入札締切",   bid_dl),
        ("開札日",     opening),
        ("申請締切",   app_dl),
    ]
    rows_html = "".join(
        f'<tr><td style="width:80px;padding:3px 8px 3px 0;color:#888;'
        f'white-space:nowrap;font-family:{font};">{label}</td>'
        f'<td style="font-family:{font};">{val}</td></tr>'
        for label, val in rows
    )

    return f"""
<div style="border:1px solid #ddd;border-radius:6px;padding:16px;
            margin-bottom:16px;background:#fff;">
  <h3 style="margin:0 0 10px;font-size:15px;color:#1a1a1a;font-family:{font};">
    {item.get("project_name", "（案件名不明）")}
  </h3>
  <table style="font-size:13px;border-collapse:collapse;width:100%;
                table-layout:fixed;">{rows_html}</table>
  {att_html}
  {link_html}
</div>"""


def build_email_html(new_items: list[dict]) -> str:
    today = datetime.now().strftime("%Y年%m月%d日")
    count = len(new_items)
    cards = "".join(build_card_email(item) for item in new_items)
    body  = cards if cards else "<p>今回の新着案件はありませんでした。</p>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Meiryo','Meiryo UI','Yu Gothic','Yu Gothic UI',sans-serif;
             max-width:660px;margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.7;">
  <div style="background:#1a3a5c;color:white;padding:20px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:18px;">入札公告 新着レポート（解体工事）</h1>
    <p style="margin:6px 0 0;font-size:13px;opacity:0.8;">{today} ／ 新着 {count} 件</p>
  </div>
  <div style="background:#f9f9f9;padding:16px;">{body}</div>
  <div style="background:#ecf0f1;padding:12px;border-radius:0 0 8px 8px;
              font-size:11px;color:#888;text-align:center;">
    情報提供元：官公需情報ポータルサイト（中小企業庁）／ 行政書士事務所ONE 自動配信
  </div>
</body>
</html>"""


def send_email(html: str, cfg: dict) -> None:
    gmail = cfg["gmail"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【入札新着】{datetime.now().strftime('%Y/%m/%d')} 解体工事レポート"
    msg["From"]    = gmail["from"]
    msg["To"]      = gmail["to"]
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail["from"], gmail["app_password"])
        smtp.send_message(msg)


# ---------------------------------------------------------------------------
# ダッシュボード HTML
# ---------------------------------------------------------------------------

def build_dashboard(all_items: list[dict]) -> str:
    today = datetime.now().strftime("%Y年%m月%d日")
    count = len(all_items)

    def card_html(item: dict) -> str:
        org      = item.get("org_name") or "—"
        area     = "".join(filter(None, [item.get("pref_name"), item.get("city_name")])) or "—"
        date     = fmt_date(item.get("cft_issue_date", ""))
        category = item.get("category") or "—"
        procedure= item.get("procedure_type") or "—"
        location = item.get("location") or "—"
        bid_dl   = fmt_jp_date(item.get("bid_deadline", ""))
        opening  = fmt_jp_date(item.get("opening_date", ""))
        app_dl   = fmt_jp_date(item.get("application_deadline", ""))
        uri      = item.get("doc_uri") or ""
        link     = f'<a href="{uri}" target="_blank" class="ext-link">公告元 →</a>' if uri else ""
        att_links = " / ".join(
            f'<a href="{a["uri"]}" target="_blank" class="ext-link">{a["name"] or "添付"}</a>'
            for a in (item.get("attachments") or []) if a.get("uri")
        )
        att_html = f'<p class="att">添付: {att_links}</p>' if att_links else ""

        return f"""
<div class="card">
  <div class="card-title">{item.get("project_name", "（案件名不明）")}</div>
  <table class="meta">
    <tr><th>発注機関</th><td>{org}</td><th>所在地</th><td>{area}</td></tr>
    <tr><th>公告日</th><td>{date}</td><th>カテゴリ</th><td>{category}</td></tr>
    <tr><th>入札方式</th><td colspan="3">{procedure}</td></tr>
    <tr><th>工事場所</th><td colspan="3">{location}</td></tr>
    <tr><th>入札締切</th><td>{bid_dl}</td><th>開札日</th><td>{opening}</td></tr>
    <tr><th>申請締切</th><td colspan="3">{app_dl}</td></tr>
  </table>
  {att_html}
  {link}
</div>"""

    cards = "".join(card_html(item) for item in all_items)
    if not cards:
        cards = '<p style="padding:16px;color:#888;">該当案件はありません。</p>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>入札公告ダッシュボード（解体工事）</title>
<style>
  body{{font-family:'Meiryo','Yu Gothic',sans-serif;max-width:960px;margin:0 auto;
        padding:20px;background:#f4f6f9;color:#1a1a1a;line-height:1.6;}}
  header{{background:#1a3a5c;color:#fff;padding:20px 24px;border-radius:8px;margin-bottom:20px;}}
  header h1{{margin:0;font-size:20px;}}
  header p{{margin:4px 0 0;font-size:13px;opacity:.8;}}
  .card{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:16px;
         margin-bottom:14px;}}
  .card-title{{font-size:15px;font-weight:bold;color:#1a3a5c;margin-bottom:10px;}}
  .meta{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;}}
  .meta th{{width:80px;color:#888;font-weight:normal;white-space:nowrap;
             padding:3px 8px 3px 0;vertical-align:top;}}
  .meta td{{padding:3px 16px 3px 0;vertical-align:top;}}
  .att{{font-size:12px;margin:4px 0;color:#555;}}
  .ext-link{{color:#2980b9;font-size:13px;display:inline-block;margin-top:6px;}}
  footer{{text-align:center;font-size:11px;color:#aaa;margin-top:24px;}}
</style>
</head>
<body>
<header>
  <h1>入札公告ダッシュボード（解体工事）</h1>
  <p>更新日: {today} ／ 直近30日 {count} 件 ／ 情報提供: 官公需情報ポータルサイト（中小企業庁）</p>
</header>
{cards}
<footer>行政書士事務所ONE 自動生成 ／ このページは検索エンジンには登録されていません</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    cfg      = load_config()
    sent_ids = load_sent_ids()

    print(f"直近{LOOKBACK_DAYS}日間の入札公告を取得中...")
    all_items = fetch_new_items()
    new_items = [item for item in all_items if item["key"] not in sent_ids]
    print(f"新着: {len(all_items)} 件（うち未送信 {len(new_items)} 件）")

    if new_items:
        print("メール送信中...")
        html = build_email_html(new_items)
        send_email(html, cfg)
        print("✓ 送信完了")

        for item in new_items:
            sent_ids[item["key"]] = {
                "cft_issue_date":       item["cft_issue_date"],
                "project_name":         item["project_name"],
                "org_name":             item["org_name"],
                "pref_name":            item["pref_name"],
                "city_name":            item["city_name"],
                "category":             item["category"],
                "procedure_type":       item.get("procedure_type", ""),
                "doc_uri":              item["doc_uri"],
                "location":             item["location"],
                "bid_deadline":         item["bid_deadline"],
                "opening_date":         item["opening_date"],
                "application_deadline": item["application_deadline"],
                "attachments":          item["attachments"],
            }
        sent_ids = prune_sent_ids(sent_ids)
        save_sent_ids(sent_ids)
        print("✓ sent_ids.json 更新")
    else:
        print("新着なし — メール送信をスキップ")

    # ダッシュボード生成（毎回更新）
    print("ダッシュボードHTML生成中...")
    dashboard_items = sorted(
        [dict(key=k, **v) for k, v in sent_ids.items()],
        key=lambda x: x.get("cft_issue_date", ""),
        reverse=True,
    )
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_dashboard(dashboard_items))
    with open(os.path.join(DOCS_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /\n")

    print(f"✓ docs/index.html 生成（{len(dashboard_items)} 件）")
    print("完了")


if __name__ == "__main__":
    main()
