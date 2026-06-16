# -*- coding: utf-8 -*-
"""
官公需情報ポータルサイト検索APIの精度・カバー範囲・最新性を確認する。
読み取り専用（GETのみ）。
"""
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://www.kkj.go.jp/api/"


def call_api(params, label):
    qs = urllib.parse.urlencode(params)
    url = f"{API_URL}?{qs}"
    print(f"\n========== {label} ==========")
    print(f"URL: {url}")
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = resp.read().decode("utf-8")

    root = ET.fromstring(data)
    error = root.find("Error")
    if error is not None:
        print(f"ERROR: {error.text}")
        return

    search_results = root.find("SearchResults")
    hits = search_results.find("SearchHits").text
    print(f"SearchHits: {hits}")

    results = search_results.findall("SearchResult")
    print(f"Returned: {len(results)}")
    for r in results:
        def get(tag):
            el = r.find(tag)
            return el.text if el is not None else "-"

        project = get("ProjectName")
        org = get("OrganizationName")
        pref = get("PrefectureName")
        city = get("CityName")
        cft = get("CftIssueDate")
        category = get("Category")
        attachments = r.find("Attachments")
        att_count = len(attachments.findall("Attachment")) if attachments is not None else 0
        print(f"- [{cft}] ({category}) {org}/{pref}/{city}: {project[:60]} (添付{att_count}件)")


# 1. 全文検索「解体」+ 工事カテゴリ + 直近1週間
call_api(
    {"Query": "解体", "Category": "2", "CFT_Issue_Date": "2026-06-08/", "Count": "20"},
    "Query=解体 Category=工事 直近(2026-06-08~)",
)

# 2. 件名検索「解体工事」のみ + 直近1週間（タイトルに「解体工事」を含むものに絞る）
call_api(
    {"Project_Name": "解体工事", "CFT_Issue_Date": "2026-06-08/", "Count": "20"},
    "Project_Name=解体工事 直近(2026-06-08~)",
)

# 3. 全文検索「解体」だが工事カテゴリ指定なし（カテゴリ未設定データの有無を確認）
call_api(
    {"Query": "解体", "CFT_Issue_Date": "2026-06-08/", "Count": "20"},
    "Query=解体 (カテゴリ指定なし) 直近(2026-06-08~)",
)

# 4. 東京都(LgCode=13)に絞った「解体」
call_api(
    {"Query": "解体", "LG_Code": "13", "CFT_Issue_Date": "2026-05-01/", "Count": "20"},
    "Query=解体 東京都(LgCode=13) 直近1ヶ月",
)
