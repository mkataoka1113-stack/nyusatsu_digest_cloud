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

LOOKBACK_DAYS         = 8    # API取得対象（直近N日間）
SENT_ID_RETENTION_DAYS = 30  # 送信済みID保持期間（ダッシュボード表示も兼ねる）
SEARCH_KEYWORDS       = ["解体"]  # 件名部分一致キーワード（増やせば拡張可）
API_COUNT             = 100  # 1回のAPI呼び出し最大件数（上限1000）


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
    """SENT_ID_RETENTION_DAYS より古い案件を削除する"""
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
# API 呼び出し
# ---------------------------------------------------------------------------

def call_api(project_name: str, since_date: str) -> list[dict]:
    """件名に project_name を含む案件を since_date 以降で取得する"""
    params = urllib.parse.urlencode({
        "Project_Name": project_name,
        "CFT_Issue_Date": f"{since_date}/",
        "Count": str(API_COUNT),
    })
    url = f"{API_URL}?{params}"
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

        results.append({
            "key":              get("Key"),
            "project_name":     get("ProjectName"),
            "org_name":         get("OrganizationName"),
            "pref_name":        get("PrefectureName"),
            "city_name":        get("CityName"),
            "cft_issue_date":   get("CftIssueDate"),
            "category":         get("Category"),
            "procedure_type":   get("ProcedureType"),
            "location":         get("Location"),
            "doc_uri":          get("ExternalDocumentURI"),
            "description":      get("ProjectDescription"),
            "tender_deadline":  get("TenderSubmissionDeadline"),
            "opening_event":    get("OpeningTendersEvent"),
            "period_end":       get("PeriodEndTime"),
            "attachments":      attachments,
        })
    return results


def fetch_new_items() -> list[dict]:
    """全キーワードを検索し、直近LOOKBACK_DAYS日間の案件をIDで重複除去して返す"""
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    seen: set[str] = set()
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

    # 公告日の新しい順にソート
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
        return iso_str


def truncate(text: str, length: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:length] + "…" if len(text) > length else text


# ---------------------------------------------------------------------------
# メール
# ---------------------------------------------------------------------------

def build_card_email(item: dict) -> str:
    font = "'Yu Gothic','Yu Gothic UI',sans-serif"
    org  = item["org_name"] or "—"
    area = "".join(filter(None, [item["pref_name"], item["city_name"]])) or "—"
    date = fmt_date(item["cft_issue_date"])
    category = item["category"] or "—"
    deadline = fmt_date(item["tender_deadline"])
    opening  = fmt_date(item["opening_event"])
    desc = truncate(item["description"], 250) if item["description"] else "（公告文なし）"
    uri  = item["doc_uri"] or ""
    link_html = (
        f'<p style="margin:8px 0 0;font-family:{font};">'
        f'<a href="{uri}" style="color:#2980b9;font-size:13px;">公告元ページを見る →</a></p>'
        if uri else ""
    )

    att_html = ""
    if item["attachments"]:
        links = []
        for att in item["attachments"]:
            if att["uri"]:
                label = att["name"] or "添付ファイル"
                links.append(f'<a href="{att["uri"]}" style="color:#2980b9;">{label}</a>')
        if links:
            att_html = (
                f'<p style="margin:6px 0 0;font-size:12px;color:#555;font-family:{font};">'
                f'添付: {" / ".join(links)}</p>'
            )

    rows = [
        ("発注機関", org),
        ("所在地", area),
        ("公告日", date),
        ("カテゴリ", category),
        ("入札締切", deadline),
        ("開札日", opening),
    ]
    rows_html = "".join(
        f'<tr><td style="width:80px;padding:3px 10px 3px 0;color:#888;white-space:nowrap;font-family:{font};">{label}</td>'
        f'<td style="font-family:{font};">{val}</td></tr>'
        for label, val in rows
    )

    return f"""
<div style="border:1px solid #ddd;border-radius:6px;padding:16px;
            margin-bottom:16px;background:#fff;">
  <h3 style="margin:0 0 8px;font-size:15px;color:#1a1a1a;font-family:{font};">{item["project_name"]}</h3>
  <table style="font-size:13px;border-collapse:collapse;width:100%;table-layout:fixed;">{rows_html}</table>
  <p style="margin:10px 0 4px;font-size:12px;color:#555;font-family:{font};">{desc}</p>
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
        org   = item["org_name"] or "—"
        area  = "".join(filter(None, [item["pref_name"], item["city_name"]])) or "—"
        date  = fmt_date(item["cft_issue_date"])
        deadline = fmt_date(item["tender_deadline"])
        opening  = fmt_date(item["opening_event"])
        category = item["category"] or "—"
        desc  = truncate(item["description"], 200) if item["description"] else ""
        uri   = item["doc_uri"] or ""
        link  = (f'<a href="{uri}" target="_blank" class="ext-link">公告元 →</a>'
                 if uri else "")
        att_links = " / ".join(
            f'<a href="{a["uri"]}" target="_blank" class="ext-link">{a["name"] or "添付"}</a>'
            for a in item["attachments"] if a.get("uri")
        )
        att_html = f'<p class="att">{att_links}</p>' if att_links else ""

        return f"""
<div class="card">
  <div class="card-title">{item["project_name"]}</div>
  <table class="meta">
    <tr><th>発注機関</th><td>{org}</td><th>所在地</th><td>{area}</td></tr>
    <tr><th>公告日</th><td>{date}</td><th>カテゴリ</th><td>{category}</td></tr>
    <tr><th>入札締切</th><td>{deadline}</td><th>開札日</th><td>{opening}</td></tr>
  </table>
  <p class="desc">{desc}</p>
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
  body{{font-family:'Meiryo','Yu Gothic',sans-serif;max-width:900px;margin:0 auto;
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
  .desc{{font-size:12px;color:#555;margin:8px 0 6px;}}
  .att{{font-size:12px;margin:4px 0;}}
  .ext-link{{color:#2980b9;font-size:13px;}}
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
    cfg = load_config()
    sent_ids = load_sent_ids()

    print(f"直近{LOOKBACK_DAYS}日間の入札公告を取得中...")
    all_items  = fetch_new_items()
    new_items  = [item for item in all_items if item["key"] not in sent_ids]
    print(f"新着: {len(all_items)} 件（うち未送信 {len(new_items)} 件）")

    if new_items:
        print("メール送信中...")
        html = build_email_html(new_items)
        send_email(html, cfg)
        print("✓ 送信完了")

        for item in new_items:
            sent_ids[item["key"]] = {
                "cft_issue_date": item["cft_issue_date"],
                "project_name":   item["project_name"],
                "org_name":       item["org_name"],
                "pref_name":      item["pref_name"],
                "city_name":      item["city_name"],
                "category":       item["category"],
                "doc_uri":        item["doc_uri"],
                "tender_deadline": item["tender_deadline"],
                "opening_event":  item["opening_event"],
                "description":    item["description"][:300] if item["description"] else "",
                "attachments":    item["attachments"],
            }
        sent_ids = prune_sent_ids(sent_ids)
        save_sent_ids(sent_ids)
        print("✓ sent_ids.json 更新")
    else:
        print("新着なし — メール送信をスキップ")

    # ダッシュボード生成（新着の有無にかかわらず毎回更新）
    print("ダッシュボードHTML生成中...")
    # sent_ids 内の全案件を公告日降順で並べて表示
    dashboard_items = sorted(
        [dict(key=k, **v) for k, v in sent_ids.items()],
        key=lambda x: x.get("cft_issue_date", ""),
        reverse=True,
    )
    os.makedirs(DOCS_DIR, exist_ok=True)
    index_path   = os.path.join(DOCS_DIR, "index.html")
    robots_path  = os.path.join(DOCS_DIR, "robots.txt")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(build_dashboard(dashboard_items))

    with open(robots_path, "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /\n")

    print(f"✓ {index_path} 生成（{len(dashboard_items)} 件）")
    print("完了")


if __name__ == "__main__":
    main()
