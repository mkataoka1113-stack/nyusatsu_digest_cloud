# -*- coding: utf-8 -*-
"""
官公需情報ポータルAPIが、東京都庁・東京都住宅供給公社(JKK)など、
ご指定の各システムの発注機関をカバーしているか確認する。
読み取り専用（GETのみ）。
"""
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://www.kkj.go.jp/api/"


def call_api(params, label, show=20):
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
        uri = get("ExternalDocumentURI")
        print(f"- [{cft}] {org}: {project[:50]}")
        print(f"    URI: {uri[:100]}")


# 1. 東京都庁本体（機関名検索）
call_api(
    {"Organization_Name": "東京都", "Project_Name": "解体", "CFT_Issue_Date": "2025-01-01/", "Count": "20"},
    "Organization_Name=東京都 Project_Name=解体 (2025年以降)",
)

# 2. 東京都住宅供給公社(JKK)
call_api(
    {"Organization_Name": "住宅供給公社", "CFT_Issue_Date": "2025-01-01/", "Count": "20"},
    "Organization_Name=住宅供給公社 (2025年以降)",
)

# 3. 東京都全体で直近の「解体」(機関名問わず、都道府県コード13)
call_api(
    {"Project_Name": "解体", "LG_Code": "13", "CFT_Issue_Date": "2025-01-01/", "Count": "30"},
    "LgCode=13(東京都) Project_Name=解体 (2025年以降)",
)
