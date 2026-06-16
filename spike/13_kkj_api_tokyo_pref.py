# -*- coding: utf-8 -*-
"""
東京都庁本体・JKK(東京都住宅供給公社)が、kkj.go.jp APIに
そもそも存在するか（解体以外のキーワードでも）を確認する。
読み取り専用（GETのみ）。
"""
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://www.kkj.go.jp/api/"


def call_api(params, label, show=15):
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
    orgs = set()
    for r in results[:show]:
        def get(tag):
            el = r.find(tag)
            return el.text if el is not None else "-"
        org = get("OrganizationName")
        project = get("ProjectName")
        cft = get("CftIssueDate")
        print(f"- [{cft}] {org}: {project[:50]}")
        orgs.add(org)


# 1. 機関名「東京都」のみ（解体限定なし）で都庁本体が出るか
call_api(
    {"Organization_Name": "東京都", "Category": "2", "CFT_Issue_Date": "2026-06-01/", "Count": "15"},
    "Organization_Name=東京都 Category=工事 直近(2026-06-01~)",
)

# 2. 機関名「東京都　建設局」「東京都　財務局」など本庁部局名で直接検索
for org in ["東京都建設局", "東京都財務局", "東京都港湾局", "東京都都市整備局"]:
    call_api(
        {"Organization_Name": org, "CFT_Issue_Date": "2025-01-01/", "Count": "5"},
        f"Organization_Name={org} (2025年以降)",
    )

# 3. JKK / 東京都住宅供給公社 表記ゆれ確認
for org in ["JKK", "東京都住宅供給公社", "住宅供給公社東京都"]:
    call_api(
        {"Organization_Name": org, "CFT_Issue_Date": "2024-01-01/", "Count": "5"},
        f"Organization_Name={org} (2024年以降)",
    )
