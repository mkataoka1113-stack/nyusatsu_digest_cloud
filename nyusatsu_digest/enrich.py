"""
nyusatsu_digest/enrich.py

公告PDF・詳細ページテキストから、AI（Gemini → Groq フォールバック）で
予定価格・地域要件・工期・締切・概要を構造化抽出する。
economic-dashboard の scripts/analyze.py と同じ無料枠APIの2段構え。

設計方針:
- AIに送るのは入札公告等の「公開情報」のみ。clients.json などの
  クライアント情報は絶対にプロンプトへ含めない。
- 文書に明記されていない項目は null（推測で値を作らせない）。
- 抽出結果は sent_ids.json の entry["enrich"] にキャッシュし、1案件1回だけ処理する。
- APIキー未設定・全プロバイダー失敗でも例外を上げず、従来の配信動作を維持する。
- 締切日時は既存スクレイパーの構造化データを優先し、空欄の補完のみに使う（digest.py 側）。
"""
import io
import json
import os
import re
import time
import urllib.request
import zipfile
from base64 import b64encode
from datetime import datetime, timezone

MAX_ENRICH_PER_RUN = 30        # 1回の実行でAI抽出する案件数の上限（暴走防止）
MAX_DOWNLOADS_PER_ITEM = 2     # 1案件あたりのPDFダウンロード数上限
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PROMPT_CHARS = 12000       # プロンプトに載せる公告テキストの上限
MIN_TEXT_CHARS = 120           # これ未満なら抽出素材不足として no_text 扱い
LLM_INTERVAL_SEC = 6           # Gemini無料枠のレート制限（10 RPM）に収める間隔

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"

USER_AGENT = "Mozilla/5.0 (compatible; nyusatsu-digest/1.0)"


# ---------------------------------------------------------------------------
# ファイル取得・テキスト化
# ---------------------------------------------------------------------------

def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read(MAX_FILE_BYTES)


def _pdf_to_text(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception as e:
        print(f"  [enrich] PDFテキスト抽出失敗: {e}")
        return ""


def _zip_to_text(data: bytes) -> str:
    texts = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        for n in zf.namelist():
            if n.lower().endswith(".pdf"):
                texts.append(_pdf_to_text(zf.read(n)))
            if len(texts) >= 3:
                break
    except Exception as e:
        print(f"  [enrich] zip展開失敗: {e}")
    return "\n\n".join(t for t in texts if t)


def _candidate_urls(item_dict: dict) -> list[str]:
    """公告本文がありそうなURLを優先度順に返す（PDF直リンクのみ）"""
    urls = []
    doc_uri = item_dict.get("doc_uri") or ""
    if doc_uri.lower().split("?")[0].endswith(".pdf"):
        urls.append(doc_uri)
    atts = sorted(
        item_dict.get("attachments") or [],
        key=lambda a: 0 if "公告" in (a.get("name") or "") else 1,
    )
    for a in atts:
        uri = a.get("uri") or ""
        ext = uri.lower().split("?")[0]
        if ext.endswith(".pdf") or ext.endswith(".zip"):
            urls.append(uri)
    # 重複除去（順序維持）
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _gather_text(item_dict: dict, detail_text: str) -> tuple[str, bytes | None]:
    """抽出素材テキストと、テキスト化できなかった場合のPDFバイト列（Gemini直読み用）を返す"""
    parts = []
    if detail_text and detail_text.strip():
        parts.append(detail_text.strip())

    scanned_pdf = None
    downloads = 0
    for url in _candidate_urls(item_dict):
        if downloads >= MAX_DOWNLOADS_PER_ITEM:
            break
        try:
            data = _download(url)
            downloads += 1
        except Exception as e:
            print(f"  [enrich] ダウンロード失敗 {url[:60]}: {e}")
            continue
        ext = url.lower().split("?")[0]
        text = _zip_to_text(data) if ext.endswith(".zip") else _pdf_to_text(data)
        if text and len(text.strip()) > 100:
            parts.append(text.strip())
        elif ext.endswith(".pdf") and scanned_pdf is None:
            # テキストが取れない=スキャン画像PDFの可能性。Gemini直読み用に保持
            scanned_pdf = data
        time.sleep(0.5)

    return "\n\n".join(parts), scanned_pdf


# ---------------------------------------------------------------------------
# LLM 呼び出し（Gemini → Groq フォールバック）
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """あなたは日本の公共工事の入札公告から情報を抽出するアシスタントです。
以下の公告文書から情報を抽出し、JSONのみを出力してください。

ルール:
- 文書に明記されていない項目は必ず null にする。推測や補完で値を作らない。
- planned_price: 予定価格。金額・税区分を原文どおり抜き出す（例: "139,557,000円（税込）"）。
  「事後公表」「落札決定後公表」等の記載ならその文言を入れる。記載がなければ null。
- region_requirement: 入札参加資格のうち、本店・支店・営業所の所在地に関する要件のみを
  原文に忠実に短くまとめる（例: "千代田区内に本店または営業所を有すること"）。
  所在地に関する要件の記載がなければ null（等級・実績などの要件はここに含めない）。
- koki: 工期・履行期間を原文どおり短く（例: "契約確定の翌日から2028年3月31日まで"）。
- application_deadline: 入札参加申請・希望申請の締切。"YYYY-MM-DD" または "YYYY-MM-DDTHH:MM" 形式。
- bid_deadline: 入札書提出の締切。同上の形式。
- summary: 工事内容の概要を日本語2〜3文で。文書に書かれた事実のみを使う。
- 令和N年 は 2018+N 年に換算する（令和8年=2026年）。

出力形式（このJSONのみを出力）:
{"planned_price": ..., "region_requirement": ..., "koki": ..., "application_deadline": ..., "bid_deadline": ..., "summary": ...}

=== 公告文書 ===
"""


def _call_gemini(prompt: str, pdf_data: bytes | None = None) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 未設定")
    parts = [{"text": prompt}]
    if pdf_data:
        parts.append({"inline_data": {
            "mime_type": "application/pdf",
            "data": b64encode(pdf_data).decode("ascii"),
        }})
    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1},
    }).encode("utf-8")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={api_key}")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(prompt: str, pdf_data: bytes | None = None) -> str:
    if pdf_data:
        raise ValueError("GroqはPDF直読み非対応")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY 未設定")
    # urllib だと Cloudflare にブロックされる（error code: 1010）ため requests を使う
    import requests
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None


def _llm_extract(text: str, pdf_data: bytes | None = None) -> tuple[dict | None, str]:
    prompt = PROMPT_TEMPLATE + text[:MAX_PROMPT_CHARS]
    providers = [("gemini", _call_gemini), ("groq", _call_groq)]
    for name, func in providers:
        for attempt in (1, 2):
            try:
                raw = func(prompt, pdf_data)
                result = _parse_json(raw)
                if result is not None:
                    return result, name
                print(f"  [enrich] {name}: JSON解析失敗（試行{attempt}）")
            except ValueError as e:
                print(f"  [enrich] {name}: {e}、スキップ")
                break
            except Exception as e:
                print(f"  [enrich] {name} 失敗（試行{attempt}）: {e}")
                if attempt == 1:
                    time.sleep(10)
    return None, ""


# ---------------------------------------------------------------------------
# 抽出結果の検証
# ---------------------------------------------------------------------------

def _clean_str(val, max_len: int) -> str | None:
    if not isinstance(val, str):
        return None
    s = " ".join(val.split()).strip()
    if not s or s.lower() in ("null", "none", "なし", "不明", "記載なし"):
        return None
    return s[:max_len]


def _clean_date(val) -> str | None:
    if not isinstance(val, str) or not val.strip():
        return None
    s = val.strip().replace("/", "-")
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})([T\s](\d{1,2}):(\d{2}))?", s)
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(4):
            dt = datetime(y, mo, d, int(m.group(5)), int(m.group(6)))
        else:
            dt = datetime(y, mo, d)
        # 公告として非常識な年は誤抽出とみなして捨てる
        if not (2020 <= dt.year <= 2040):
            return None
        return dt.isoformat()
    except ValueError:
        return None


def _validate(result: dict) -> dict:
    price = _clean_str(result.get("planned_price"), 60)
    # 金額らしさの確認: 数字か「公表/公開」系の文言を含まないものは捨てる
    if price and not (re.search(r"\d", price) or "公表" in price or "公開" in price):
        price = None
    return {
        "planned_price":        price,
        "region_requirement":   _clean_str(result.get("region_requirement"), 200),
        "koki":                 _clean_str(result.get("koki"), 80),
        "application_deadline": _clean_date(result.get("application_deadline")),
        "bid_deadline":         _clean_date(result.get("bid_deadline")),
        "summary":              _clean_str(result.get("summary"), 400),
    }


# ---------------------------------------------------------------------------
# メイン: 新規案件の抽出
# ---------------------------------------------------------------------------

def enrich_new_items(all_items: list, sent_ids: dict) -> None:
    """新規（enrich 未処理）の案件についてAI抽出を行い、sent_ids の entry に書き込む。
    all_items は BidItem のリスト（detail_text はここからのみ参照し、保存しない）。"""
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        print("[enrich] APIキー未設定のためAI抽出をスキップします")
        return

    targets = [i for i in all_items
               if i.key in sent_ids and "enrich" not in sent_ids[i.key]]
    if not targets:
        print("[enrich] 抽出対象なし")
        return
    capped = targets[:MAX_ENRICH_PER_RUN]
    print(f"[enrich] AI抽出対象: {len(capped)} 件"
          + (f"（上限適用、残り{len(targets) - len(capped)}件は次回）" if len(targets) > len(capped) else ""))

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i, item in enumerate(capped):
        entry = sent_ids[item.key]
        enrich: dict = {"status": "", "provider": "", "enriched_at": now}
        try:
            text, scanned_pdf = _gather_text(entry, getattr(item, "detail_text", ""))
            if len(text.strip()) < MIN_TEXT_CHARS and not scanned_pdf:
                enrich["status"] = "no_text"
                entry["enrich"] = enrich
                print(f"  ({i+1}/{len(capped)}) 素材なし: {item.project_name[:30]}")
                continue

            pdf_for_vision = scanned_pdf if len(text.strip()) < MIN_TEXT_CHARS else None
            result, provider = _llm_extract(text, pdf_for_vision)
            if result is None:
                enrich["status"] = "llm_failed"
                entry["enrich"] = enrich
                print(f"  ({i+1}/{len(capped)}) AI失敗: {item.project_name[:30]}")
                continue

            fields = _validate(result)
            enrich.update(fields)
            enrich["status"] = "ok"
            enrich["provider"] = provider
            entry["enrich"] = enrich

            # 締切は既存スクレイパー値を優先し、空欄のみAI値で補完する
            if not entry.get("application_deadline") and fields["application_deadline"]:
                entry["application_deadline"] = fields["application_deadline"]
            if not entry.get("bid_deadline") and fields["bid_deadline"]:
                entry["bid_deadline"] = fields["bid_deadline"]

            got = [k for k in ("planned_price", "region_requirement", "summary") if fields[k]]
            print(f"  ({i+1}/{len(capped)}) OK[{provider}] {item.project_name[:30]} 取得: {','.join(got) or 'なし'}")
        except Exception as e:
            enrich["status"] = "error"
            entry["enrich"] = enrich
            print(f"  ({i+1}/{len(capped)}) 例外: {item.project_name[:30]}: {e}")

        time.sleep(LLM_INTERVAL_SEC)
