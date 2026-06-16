# -*- coding: utf-8 -*-
"""
件名検索(Project_Name)の精度・カバー範囲をさらに確認する。
読み取り専用（GETのみ）。
"""
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://www.kkj.go.jp/api/"


def call_api(params, label, show=30):
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
    for r in results[:show]:
        def get(tag):
            el = r.find(tag)
            return el.text if el is not None else "-"

        project = get("ProjectName")
        org = get("OrganizationName")
        cft = get("CftIssueDate")
        category = get("Category")
        print(f"- [{cft}] ({category}) {org}: {project[:70]}")


# 1. 件名検索「解体」（工事限定なし）直近1週間、件数を多めに
call_api(
    {"Project_Name": "解体", "CFT_Issue_Date": "2026-06-05/", "Count": "100"},
    "Project_Name=解体 直近(2026-06-05~) 全件数確認",
)

# 2. 「撤去」も別キーワードとしてどれくらい出るか（解体とは別表現の取り逃しチェック）
call_api(
    {"Project_Name": "撤去", "CFT_Issue_Date": "2026-06-05/", "Count": "30"},
    "Project_Name=撤去 直近(2026-06-05~)",
)

# 3. 1日だけのデータ量感（全国・解体タイトル）
call_api(
    {"Project_Name": "解体", "CFT_Issue_Date": "2026-06-12", "Count": "100"},
    "Project_Name=解体 2026-06-12のみ",
)
