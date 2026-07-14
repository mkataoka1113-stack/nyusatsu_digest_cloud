"""
scrapers/__init__.py

全スクレイパーが返す共通型 BidItem と、
都道府県名→コードの変換マップを定義する。
"""
from dataclasses import dataclass, field

PREF_NAME_TO_CODE: dict[str, str] = {
    "北海道": "01", "青森県": "02", "岩手県": "03", "宮城県": "04",
    "秋田県": "05", "山形県": "06", "福島県": "07", "茨城県": "08",
    "栃木県": "09", "群馬県": "10", "埼玉県": "11", "千葉県": "12",
    "東京都": "13", "神奈川県": "14", "新潟県": "15", "富山県": "16",
    "石川県": "17", "福井県": "18", "山梨県": "19", "長野県": "20",
    "岐阜県": "21", "静岡県": "22", "愛知県": "23", "三重県": "24",
    "滋賀県": "25", "京都府": "26", "大阪府": "27", "兵庫県": "28",
    "奈良県": "29", "和歌山県": "30", "鳥取県": "31", "島根県": "32",
    "岡山県": "33", "広島県": "34", "山口県": "35", "徳島県": "36",
    "香川県": "37", "愛媛県": "38", "高知県": "39", "福岡県": "40",
    "佐賀県": "41", "長崎県": "42", "熊本県": "43", "大分県": "44",
    "宮崎県": "45", "鹿児島県": "46", "沖縄県": "47",
}


@dataclass
class BidItem:
    source:               str        # "kkj" | "etokyo"
    key:                  str        # ユニークID（kkj=APIキー、etokyo="etokyo_YYYY:13:CCC:NNNNN"）
    project_name:         str
    org_name:             str
    pref_name:            str        # 都道府県名（例: "東京都"）
    city_name:            str        # 市区町村名（例: "荒川区"）
    pref_code:            str        # 都道府県コード（例: "13"）
    gyoshu_codes:         list       # 業種コードリスト（例: ["3100"]）
    cft_issue_date:       str        # 公告日（ISO 8601 or "YYYY/MM/DD HH:MM"）
    procedure_type:       str        # 入札方式
    doc_uri:              str        # 公告元URL
    attachments:          list       # [{"name": str, "uri": str}, ...]
    location:             str        # 工事場所
    bid_deadline:         str        # 入札締切
    opening_date:         str        # 開札日
    application_deadline: str        # 申請締切
    # 詳細ページ本文＋公告PDFのテキスト。AI抽出（enrich）の素材として同一実行内でのみ使い、
    # sent_ids.json には保存しない（公開リポジトリの肥大化を防ぐため to_dict に含めない）
    detail_text:          str = ""
    # ダウンロード済みの入札公告PDF [{"name": str, "data": bytes}, ...]。
    # digest.py が docs/files/ に保存してダッシュボード・メールにリンクを埋め込む。
    # bytes を含むため to_dict には含めない（同一実行内でのみ使用）
    kokoku_files:         list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source":               self.source,
            "key":                  self.key,
            "project_name":         self.project_name,
            "org_name":             self.org_name,
            "pref_name":            self.pref_name,
            "city_name":            self.city_name,
            "pref_code":            self.pref_code,
            "gyoshu_codes":         self.gyoshu_codes,
            "cft_issue_date":       self.cft_issue_date,
            "procedure_type":       self.procedure_type,
            "doc_uri":              self.doc_uri,
            "attachments":          self.attachments,
            "location":             self.location,
            "bid_deadline":         self.bid_deadline,
            "opening_date":         self.opening_date,
            "application_deadline": self.application_deadline,
        }
