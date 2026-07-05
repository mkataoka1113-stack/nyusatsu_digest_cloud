"""
nyusatsu_digest/digest.py

複数スクレイパーから入札公告を収集し、
clients.json の設定に基づいてクライアント別にメール配信する。
GitHub Pages 用ダッシュボード HTML も生成する。

実行:
  python nyusatsu_digest/digest.py
"""
import html as html_mod
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH   = os.path.join(BASE_DIR, "config.json")
CLIENTS_PATH  = os.path.join(BASE_DIR, "clients.json")
SENT_IDS_PATH = os.path.join(BASE_DIR, "sent_ids.json")
DOCS_DIR      = os.path.join(os.path.dirname(BASE_DIR), "docs")

SENT_ID_RETENTION_DAYS = 30
LOOKBACK_DAYS          = 8
JST = timezone(timedelta(hours=9))  # GitHub ActionsランナーはUTCのため日付表示はJST固定


# ---------------------------------------------------------------------------
# 設定・クライアント・送信済みID
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


def load_clients() -> list[dict]:
    if not os.path.exists(CLIENTS_PATH):
        print("[警告] clients.json が見つかりません。config.json の to: を使います。")
        return []
    with open(CLIENTS_PATH, encoding="utf-8") as f:
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
    """重複送信を防ぐための保持期間は、案件の公告日ではなく「自分がいつ検知したか」
    （fetched_date）を基準にする。公告日基準だと、検知時点で既に公告日が古い案件
    （都庁本体の発注予定情報など）が送信直後にここで消えてしまい、次回また
    「未送信の新着」として誤検知され再送されてしまう。"""
    threshold = datetime.now(timezone.utc) - timedelta(days=SENT_ID_RETENTION_DAYS)
    pruned = {}
    for key, entry in sent_ids.items():
        date_str = entry.get("fetched_date") or entry.get("cft_issue_date", "")
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= threshold:
                pruned[key] = entry
        except (ValueError, AttributeError):
            pruned[key] = entry  # パース失敗は残す
    return pruned


# ---------------------------------------------------------------------------
# 重複排除（自治体独自システムを優先）
# ---------------------------------------------------------------------------

def dedupe_prefer_local(items: list) -> list:
    """同一案件が kkj.go.jp（全国ポータル）と自治体独自システムの両方に
    掲載されている場合、自治体独自システム側を優先して kkj 側を除外する。
    案件名＋自治体名が完全一致するものを同一案件とみなす。"""
    groups: dict[tuple[str, str], list] = {}
    for item in items:
        key = (item.project_name.strip(), (item.city_name or "").strip())
        groups.setdefault(key, []).append(item)

    result = []
    for group in groups.values():
        if len(group) > 1:
            non_kkj = [i for i in group if i.source != "kkj"]
            if non_kkj:
                result.extend(non_kkj)
                continue
        result.extend(group)
    return result


# ---------------------------------------------------------------------------
# フィルター判定
# ---------------------------------------------------------------------------

def matches_filters(item_dict: dict, filters: dict) -> bool:
    """clients.json の filters に案件がマッチするか判定する"""
    if not filters:
        return True  # フィルターなし = 全件受信

    # 業種コードフィルター
    if filters.get("gyoshu_codes"):
        item_gyoshu = item_dict.get("gyoshu_codes", [])
        if not any(code in item_gyoshu for code in filters["gyoshu_codes"]):
            return False

    # 参加資格登録自治体フィルター（非空のとき優先）
    if filters.get("qualified_cities"):
        if item_dict.get("city_name") not in filters["qualified_cities"]:
            return False
    elif filters.get("pref_codes"):
        # qualified_cities が空なら都道府県単位でフィルター
        if item_dict.get("pref_code") not in filters["pref_codes"]:
            return False

    return True


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


def fmt_jp_date(val: str) -> str:
    if not val:
        return "—"
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        jst = dt.astimezone(timezone(timedelta(hours=9)))
        return jst.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return val


SOURCE_LABEL = {
    "kkj":        "官公需ポータル",
    "etokyo":     "e-tokyo",
    "tokyometro": "東京電子調達",
    "jkk":        "JKK",
    "chiba":      "千葉電子調達",
    "ippi":       "入札情報サービス（防衛省）",
}


# ---------------------------------------------------------------------------
# メール生成
# ---------------------------------------------------------------------------

def build_card_email(item: dict) -> str:
    esc      = html_mod.escape
    font     = "'Yu Gothic','Yu Gothic UI',sans-serif"
    org      = esc(item.get("org_name") or "—")
    area     = esc("".join(filter(None, [item.get("pref_name"), item.get("city_name")])) or "—")
    date     = fmt_date(item.get("cft_issue_date", ""))
    procedure= esc(item.get("procedure_type") or "—")
    location = esc(item.get("location") or "—")
    bid_dl   = fmt_jp_date(item.get("bid_deadline", ""))
    opening  = fmt_jp_date(item.get("opening_date", ""))
    app_dl   = fmt_jp_date(item.get("application_deadline", ""))
    uri      = esc(item.get("doc_uri") or "")
    source   = esc(SOURCE_LABEL.get(item.get("source", ""), item.get("source", "")))

    link_html = (
        f'<p style="margin:8px 0 0;font-family:{font};">'
        f'<a href="{uri}" style="color:#2980b9;font-size:13px;">公告元ページを見る →</a></p>'
        if uri else ""
    )
    att_links = " / ".join(
        f'<a href="{esc(a["uri"])}" style="color:#2980b9;">{esc(a["name"] or "添付ファイル")}</a>'
        for a in (item.get("attachments") or []) if a.get("uri")
    )
    att_html = (
        f'<p style="margin:4px 0;font-size:12px;color:#555;font-family:{font};">'
        f'添付: {att_links}</p>'
        if att_links else ""
    )
    rows = [
        ("発注機関",  org),
        ("所在地",    area),
        ("公告日",    date),
        ("入札方式",  procedure),
        ("工事場所",  location),
        ("申請締切",  app_dl),
        ("入札締切",  bid_dl),
        ("開札日",    opening),
        ("情報源",    source),
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
    {esc(item.get("project_name", "（案件名不明）"))}
  </h3>
  <table style="font-size:13px;border-collapse:collapse;width:100%;
                table-layout:fixed;">{rows_html}</table>
  {att_html}
  {link_html}
</div>"""


def build_email_html(client: dict, items: list[dict]) -> str:
    today = datetime.now(JST).strftime("%Y年%m月%d日")
    count = len(items)
    name  = client.get("name", "")
    cards = "".join(build_card_email(item) for item in items)
    body  = cards if cards else "<p>今回の新着案件はありませんでした。</p>"
    gyoshu_label = "・".join(
        client.get("filters", {}).get("gyoshu_codes", []) or ["全業種"]
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Meiryo','Yu Gothic',sans-serif;
             max-width:660px;margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.7;">
  <div style="background:#1a3a5c;color:white;padding:20px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:18px;">入札公告 新着レポート</h1>
    <p style="margin:6px 0 0;font-size:13px;opacity:0.8;">
      {today} ／ {name} 向け ／ 新着 {count} 件 ／ 業種: {gyoshu_label}
    </p>
  </div>
  <div style="background:#f9f9f9;padding:16px;">{body}</div>
  <div style="background:#ecf0f1;padding:12px;border-radius:0 0 8px 8px;
              font-size:11px;color:#888;text-align:center;">
    行政書士事務所ONE 自動配信 ／
    情報提供: 官公需情報ポータルサイト（中小企業庁）・東京都電子調達サービス
  </div>
</body>
</html>"""


def send_email(html: str, client: dict, cfg: dict, subject: str | None = None) -> None:
    gmail   = cfg["gmail"]
    today   = datetime.now(JST).strftime("%Y/%m/%d")
    name    = client.get("name", "")
    msg     = MIMEMultipart("alternative")
    msg["Subject"] = subject or f"【入札新着】{today} {name} 向けレポート"
    msg["From"]    = gmail["from"]
    msg["To"]      = client["email"]
    if client.get("cc"):
        msg["Cc"] = ", ".join(client["cc"])
    msg.attach(MIMEText(html, "html", "utf-8"))

    to_addrs = [client["email"]] + client.get("cc", [])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail["from"], gmail["app_password"])
        smtp.sendmail(gmail["from"], to_addrs, msg.as_string())


def build_error_email_html(errors: list[tuple[str, str]]) -> str:
    today = datetime.now(JST).strftime("%Y年%m月%d日")
    rows = "".join(
        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee;'
        f'font-weight:bold;white-space:nowrap;">{html_mod.escape(name)}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #eee;color:#c0392b;">{html_mod.escape(msg)}</td></tr>'
        for name, msg in errors
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Meiryo','Yu Gothic',sans-serif;
             max-width:660px;margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.7;">
  <div style="background:#c0392b;color:white;padding:20px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:18px;">入札公告ダイジェスト 取得エラー通知</h1>
    <p style="margin:6px 0 0;font-size:13px;opacity:0.9;">{today} ／ {len(errors)} 件のスクレイパーでエラーが発生しました</p>
  </div>
  <div style="background:#f9f9f9;padding:16px;">
    <p style="font-size:13px;color:#555;">
      以下のシステムから今回データを取得できませんでした。サイト側の仕様変更などが原因の可能性があります。
      他のシステムの取得・メール配信には影響していません。
    </p>
    <table style="font-size:13px;border-collapse:collapse;width:100%;background:#fff;
                  border-radius:6px;overflow:hidden;border:1px solid #eee;">
      {rows}
    </table>
  </div>
  <div style="background:#ecf0f1;padding:12px;border-radius:0 0 8px 8px;
              font-size:11px;color:#888;text-align:center;">
    行政書士事務所ONE 自動配信
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# ダッシュボード HTML
# ---------------------------------------------------------------------------

def build_dashboard(all_items: list[dict]) -> str:
    today = datetime.now(JST).strftime("%Y年%m月%d日")
    count = len(all_items)

    def badge(source: str) -> str:
        # (背景色, 文字色)。黄色系のみ白文字だと読めないため文字色を濃くする
        colors = {"kkj":        ("#34495e", "#fff"),
                  "etokyo":     ("#2980b9", "#fff"),
                  "tokyometro": ("#27ae60", "#fff"),
                  "jkk":        ("#f1c40f", "#5b4a00"),
                  "chiba":      ("#e67e22", "#fff"),
                  "ippi":       ("#8e44ad", "#fff")}
        label = SOURCE_LABEL.get(source, source)
        bg, fg = colors.get(source, ("#888", "#fff"))
        return (f'<span style="background:{bg};color:{fg};font-size:11px;'
                f'padding:2px 6px;border-radius:3px;margin-right:6px;">{label}</span>')

    def card_html(item: dict) -> str:
        esc       = html_mod.escape
        org       = esc(item.get("org_name") or "—")
        area      = esc("".join(filter(None, [item.get("pref_name"), item.get("city_name")])) or "—")
        date      = fmt_date(item.get("cft_issue_date", ""))
        procedure = esc(item.get("procedure_type") or "—")
        location  = esc(item.get("location") or "—")
        bid_dl    = fmt_jp_date(item.get("bid_deadline", ""))
        opening   = fmt_jp_date(item.get("opening_date", ""))
        app_dl    = fmt_jp_date(item.get("application_deadline", ""))
        uri       = esc(item.get("doc_uri") or "")
        src       = item.get("source", "")
        link      = f'<a href="{uri}" target="_blank" class="ext-link">公告元 →</a>' if uri else ""
        att_links = " / ".join(
            f'<a href="{esc(a["uri"])}" target="_blank" class="ext-link">{esc(a["name"] or "添付")}</a>'
            for a in (item.get("attachments") or []) if a.get("uri")
        )
        att_html  = f'<p class="att">添付: {att_links}</p>' if att_links else ""
        name      = esc(item.get("project_name", "（案件名不明）"), quote=True)
        gyoshu    = ",".join(item.get("gyoshu_codes", []))

        return f"""
<div class="card" data-name="{name}" data-area="{area}" data-gyoshu="{gyoshu}">
  <div class="card-title">{badge(src)}{name}</div>
  <table class="meta">
    <tr><th>発注機関</th><td>{org}</td><th>所在地</th><td>{area}</td></tr>
    <tr><th>公告日</th><td>{date}</td><th>入札方式</th><td>{procedure}</td></tr>
    <tr><th>工事場所</th><td colspan="3">{location}</td></tr>
    <tr><th>申請締切</th><td colspan="3">{app_dl}</td></tr>
    <tr><th>入札締切</th><td>{bid_dl}</td><th>開札日</th><td>{opening}</td></tr>
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
<title>入札公告ダッシュボード</title>
<style>
  *{{box-sizing:border-box;}}
  body{{font-family:'Meiryo','Yu Gothic',sans-serif;max-width:980px;margin:0 auto;
        padding:16px;background:#f4f6f9;color:#1a1a1a;line-height:1.6;}}
  header{{background:#1a3a5c;color:#fff;padding:20px 24px;border-radius:8px;margin-bottom:16px;}}
  header h1{{margin:0;font-size:20px;}}
  header p{{margin:4px 0 0;font-size:13px;opacity:.8;}}
  .search-bar{{display:flex;gap:8px;margin-bottom:16px;}}
  .search-bar input{{flex:1;padding:8px 12px;border:1px solid #ccc;border-radius:6px;
                      font-size:14px;font-family:inherit;}}
  .search-bar button{{padding:8px 16px;background:#1a3a5c;color:#fff;border:none;
                       border-radius:6px;cursor:pointer;font-size:14px;}}
  #count-display{{font-size:13px;color:#888;margin-bottom:12px;}}
  .card{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:16px;
         margin-bottom:12px;}}
  .card.hidden{{display:none;}}
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
  <h1>入札公告ダッシュボード</h1>
  <p>更新日: {today} ／ 直近{SENT_ID_RETENTION_DAYS}日 {count} 件
     ／ 情報提供: 官公需情報ポータルサイト（中小企業庁）・東京都電子調達サービス</p>
</header>

<div class="search-bar">
  <input type="text" id="search-input" placeholder="案件名・自治体名で検索..." oninput="filterCards()">
  <button onclick="document.getElementById('search-input').value=''; filterCards();">クリア</button>
</div>
<div id="count-display">{count} 件表示中</div>

<div id="cards-container">
{cards}
</div>

<footer>行政書士事務所ONE 自動生成 ／ このページは検索エンジンには登録されていません</footer>

<script>
function filterCards() {{
  const q = document.getElementById('search-input').value.trim().toLowerCase();
  const cards = document.querySelectorAll('.card');
  let visible = 0;
  cards.forEach(card => {{
    const name  = (card.dataset.name  || '').toLowerCase();
    const area  = (card.dataset.area  || '').toLowerCase();
    const match = !q || name.includes(q) || area.includes(q);
    card.classList.toggle('hidden', !match);
    if (match) visible++;
  }});
  document.getElementById('count-display').textContent = visible + ' 件表示中';
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    cfg     = load_config()
    clients = load_clients()

    # clients.json がない場合は config.json の to: を使うフォールバック
    if not clients:
        to_addr = cfg.get("gmail", {}).get("to", "")
        if to_addr:
            clients = [{
                "id": "kataoka", "name": "管理者",
                "email": to_addr, "cc": [], "active": True, "filters": {}
            }]

    active_clients = [c for c in clients if c.get("active", True)]

    # ── スクレイパー実行 ──
    all_items: list = []
    scraper_errors: list[tuple[str, str]] = []

    SCRAPERS = [
        ("kkj",         "kkj.go.jp（官公需情報ポータル）",        "scrapers.kkj"),
        ("etokyo",      "東京都電子調達サービス（市区町村）",      "scrapers.etokyo"),
        ("tokyo_metro", "東京都電子調達システム（都庁本体）",      "scrapers.tokyo_metro"),
        ("jkk",         "JKK東京（東京都住宅供給公社）",          "scrapers.jkk"),
        ("chiba",       "ちば電子調達システム",                   "scrapers.chiba"),
        ("ippi",        "入札情報サービス（防衛省）",              "scrapers.ippi"),
    ]
    for name, label, module_path in SCRAPERS:
        try:
            module = __import__(module_path, fromlist=["fetch"])
            all_items.extend(module.fetch(LOOKBACK_DAYS))
        except Exception as e:
            print(f"[{name}] エラー: {e}")
            scraper_errors.append((label, str(e)))

    # 同一案件が kkj と自治体独自システムの両方にある場合、自治体独自システム側を優先
    before_dedupe = len(all_items)
    all_items = dedupe_prefer_local(all_items)
    if before_dedupe != len(all_items):
        print(f"重複排除: {before_dedupe} 件 → {len(all_items)} 件（kkjとの重複分を除外）")

    print(f"\n取得合計: {len(all_items)} 件")

    # ── sent_ids 読み込み ──
    sent_ids = load_sent_ids()

    # 旧フォーマット（notified キーなし）の移行:
    # 現在の全クライアントに送信済みとして扱い、再送を防ぐ
    all_active_ids = [c["id"] for c in active_clients]
    for entry in sent_ids.values():
        if "notified" not in entry:
            entry["notified"] = list(all_active_ids)

    # 新規アイテムを sent_ids に追加（notified=[] で初期化）
    fetched_date = datetime.now(timezone.utc).date().isoformat()
    for item in all_items:
        key = item.key
        if key not in sent_ids:
            entry = item.to_dict()
            entry["fetched_date"] = fetched_date
            entry["notified"]     = []
            sent_ids[key]         = entry

    # ── クライアント別メール送信 ──
    for client in active_clients:
        client_id = client["id"]
        filters   = client.get("filters", {})

        # このクライアントに未送信かつフィルターにマッチするアイテムを抽出
        targets = [
            sent_ids[item.key]
            for item in all_items
            if matches_filters(sent_ids[item.key], filters)
            and client_id not in sent_ids[item.key].get("notified", [])
        ]

        print(f"\nクライアント「{client['name']}」: 対象 {len(targets)} 件")
        if not targets:
            print("  → 新着なし、スキップ")
            continue

        try:
            html = build_email_html(client, targets)
            send_email(html, client, cfg)
            print(f"  → メール送信完了（to: {client['email']}、cc: {client.get('cc', [])}）")
            for entry in targets:
                entry["notified"].append(client_id)
        except Exception as e:
            print(f"  → メール送信エラー: {e}")

    # ── スクレイパーエラー通知（管理者宛） ──
    if scraper_errors:
        admin = next((c for c in clients if c.get("id") == "kataoka"), None)
        if admin:
            try:
                today = datetime.now(JST).strftime("%Y/%m/%d")
                html  = build_error_email_html(scraper_errors)
                send_email(html, admin, cfg, subject=f"【入札ダイジェスト】取得エラー通知 {today}")
                print(f"\nエラー通知メール送信完了（{len(scraper_errors)} 件）")
            except Exception as e:
                print(f"\nエラー通知メール送信に失敗: {e}")
        else:
            print("\n[警告] エラー通知の送信先（id=kataoka）が clients.json に見つかりません")

    # ── sent_ids 保存 ──
    sent_ids = prune_sent_ids(sent_ids)
    save_sent_ids(sent_ids)
    print("\nsent_ids.json 更新完了")

    # ── ダッシュボード生成 ──
    print("ダッシュボードHTML生成中...")
    dashboard_items = sorted(
        list(sent_ids.values()),
        key=lambda x: x.get("cft_issue_date", ""),
        reverse=True,
    )
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_dashboard(dashboard_items))
    with open(os.path.join(DOCS_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /\n")
    print(f"docs/index.html 生成完了（{len(dashboard_items)} 件）")
    print("完了")


if __name__ == "__main__":
    main()
