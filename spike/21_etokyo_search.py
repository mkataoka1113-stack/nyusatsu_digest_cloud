"""
spike/21_etokyo_search.py

東京都電子調達サービス（e-tokyo.lg.jp）の 発注案件情報（工事）フォームに
業種コード=3100（解体工事）・全自治体で検索を送信し、結果ページの構造を確認する。

ポップアップ構造:
  - 左 select (preCategory): 大区分グループ (001〜005)
  - onclick="changeDisp" でグループ選択 → 中区分項目が追加表示される
  - 「選択 >>」ボタン (AddMember) → 右 select (selectedCategory) に追加
  - 「閉じる」ボタン (RetCategory) → 親フォームの以下フィールドを設定して閉じる
      categoryCode, categoryNm, TextgyosyuCd, selectConst, constKbnCd

フォーム送信:
  - searchSubmit('P002','3','FrmMain',this) を呼び出す（検索ボタン）

実行:
  python spike/21_etokyo_search.py
"""
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, Frame

OUT_DIR = Path(__file__).parent / "screenshots" / "etokyo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FRAMESET_URL = "https://www.e-tokyo.lg.jp/choutatu_ppij/ppij/pub"

def shot(page, name: str):
    p = OUT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(p), full_page=True)
        print(f"  [screenshot] {p.name}")
    except Exception as e:
        print(f"  [screenshot error] {e}")

def save_html(frame, name: str):
    p = OUT_DIR / f"{name}.html"
    try:
        p.write_text(frame.content(), encoding="utf-8")
        print(f"  [html] {p.name}")
    except Exception as e:
        print(f"  [html error] {e}")

def print_frames(page):
    for i, f in enumerate(page.frames):
        print(f"    frame[{i}] name={f.name!r}  url={f.url}")

def main():
    today     = datetime.now()
    since     = today - timedelta(days=30)
    date_to   = today.strftime("%Y%m%d")
    date_from = since.strftime("%Y%m%d")
    print(f"  対象期間: {date_from} ～ {date_to}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=400)
        ctx  = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        # ─── Step0: フレームセット ───
        print(f"\n[0] フレームセット: {FRAMESET_URL}")
        page.goto(FRAMESET_URL, wait_until="networkidle")
        shot(page, "10_frameset")

        left_frame = None
        for f in page.frames:
            if f.name == "FrmLeft":
                left_frame = f
                break
        if left_frame is None:
            for f in page.frames:
                if "s=P001&a=1" in f.url:
                    left_frame = f
                    break
        print(f"  左ナビ: {left_frame.name!r} {left_frame.url if left_frame else 'NOT FOUND'}")

        # ─── Step1: 発注案件情報（工事）へ ───
        print("\n[1] 左ナビ「工事」をクリック")
        # 左ナビの全リンクを列挙
        links = left_frame.query_selector_all("a")
        kouji_link = None
        for lnk in links:
            text = lnk.inner_text().strip()
            href = lnk.get_attribute("href") or ""
            print(f"  [{text}] -> {href}")
            if text == "工事" and "P002" in href and kouji_link is None:
                kouji_link = lnk

        if kouji_link:
            kouji_link.click()
        else:
            # 最初の「工事」リンク（P002,1）
            for lnk in links:
                text = lnk.inner_text().strip()
                if text == "工事":
                    lnk.click()
                    break

        page.wait_for_load_state("networkidle")

        # FrmMain を取得
        main_frame = None
        for f in page.frames:
            if f.name == "FrmMain":
                main_frame = f
                break
        print(f"  FrmMain URL: {main_frame.url if main_frame else 'NOT FOUND'}")
        if main_frame:
            save_html(main_frame, "11_form_frame")
            shot(page, "11_form_page")

        if main_frame is None:
            print("  致命的エラー: FrmMain が見つからず")
            input("Enter")
            browser.close()
            return

        # ─── Step2: 全自治体チェック ───
        print("\n[2] 「全選択」ボタンをクリック")
        try:
            all_btn = main_frame.query_selector("a:has-text('全選択'), input[value*='全選択']")
            if all_btn:
                all_btn.click()
                print("  全選択ボタンをクリック")
            else:
                main_frame.evaluate("""() => {
                    document.querySelectorAll('input[name="govCode"]').forEach(cb => cb.checked = true);
                }""")
                print("  JS でチェックボックスを全選択")
        except Exception as e:
            print(f"  エラー: {e}")

        # ─── Step3: 業種ポップアップで 3100 を選択 ───
        print("\n[3] 業種ポップアップを開く")
        with page.expect_popup() as popup_info:
            main_frame.click('a.btnL:has-text("業種の一覧表")')
        popup = popup_info.value
        popup.wait_for_load_state("networkidle")
        shot(popup, "12_popup_initial")
        print(f"  ポップアップ: {popup.url}")

        # 左 select の選択肢を確認
        options_pre = popup.eval_on_selector(
            'select[name="preCategory"]',
            'el => Array.from(el.options).map(o => `${o.value}: ${o.text.trim()}`)'
        )
        print("  preCategory 初期選択肢:", options_pre[:8])

        # 「004 その他工事（～5800）」をクリックして 3100 を展開
        print("  004 (その他工事) を選択 → changeDisp で 3100 を展開")
        popup.select_option('select[name="preCategory"]', "004")
        # changeDisp は onclick で発火するので click が必要
        popup.click('select[name="preCategory"]')
        popup.wait_for_timeout(800)
        shot(popup, "12b_popup_expanded")

        # 展開後の選択肢
        options_after = popup.eval_on_selector(
            'select[name="preCategory"]',
            'el => Array.from(el.options).map(o => `${o.value}: ${o.text.trim()}`)'
        )
        print("  004 展開後:", options_after[:20])

        # 3100 を選択
        selected_3100 = False
        for opt in options_after:
            if "3100" in opt:
                print(f"  3100 発見: {opt}")
                popup.select_option('select[name="preCategory"]', value="3100")
                selected_3100 = True
                break
        if not selected_3100:
            print("  [警告] 3100 が見つからず。選択肢を再確認:")
            print("  ", options_after)

        # 「選択 >>」ボタンをクリック → selectedCategory に移動
        print("  「選択 >>」をクリック")
        popup.click('input[value=" 選択 >> "]')
        popup.wait_for_timeout(500)

        # 右 select の内容を確認
        options_selected = popup.eval_on_selector(
            'select[name="selectedCategory"]',
            'el => Array.from(el.options).map(o => `${o.value}: ${o.text.trim()}`)'
        )
        print(f"  selectedCategory: {options_selected}")
        shot(popup, "12c_popup_selected")

        # 「閉じる」をクリック → RetCategory() が親フォームに値を設定 → popup.close()
        print("  「閉じる」をクリック")
        popup.click('a:has-text("閉じる")')
        page.wait_for_timeout(800)  # popup は window.close() で自動的に閉じる

        # 設定された値を確認
        cat_code = main_frame.evaluate("document.querySelector('input[name=\"categoryCode\"]')?.value")
        sel_const = main_frame.evaluate("document.querySelector('input[name=\"selectConst\"]')?.value")
        const_kbn = main_frame.evaluate("document.querySelector('input[name=\"constKbnCd\"]')?.value")
        txt_gyosyu = main_frame.evaluate("document.querySelector('textarea[name=\"TextgyosyuCd\"]')?.value")
        print(f"  categoryCode={cat_code!r}")
        print(f"  selectConst={sel_const!r}")
        print(f"  constKbnCd={const_kbn!r}")
        print(f"  TextgyosyuCd={txt_gyosyu!r}")

        # ─── Step4: 年度・日付をセット ───
        print(f"\n[4] 年度=2026、公表日 {date_from}～{date_to}")
        main_frame.select_option('select[name="year"]', "2026")
        main_frame.fill('input[name="pubStDate"]', date_from)
        main_frame.fill('input[name="pubEndDate"]', date_to)
        shot(page, "13_form_filled")

        # ─── Step5: 「検索」ボタンをクリック ───
        print("\n[5] 「検索」ボタンをクリック")
        main_frame.click('a.btnS.btn-Primary:has-text("検索")')
        page.wait_for_load_state("networkidle")
        shot(page, "14_result_page")

        print("  送信後フレーム一覧:")
        print_frames(page)

        result_frame = None
        for f in page.frames:
            if f.name == "FrmMain":
                result_frame = f
                break
        if result_frame is None:
            for f in page.frames:
                if "P002" in f.url:
                    result_frame = f
                    break

        if result_frame:
            print(f"  結果フレームURL: {result_frame.url}")
            save_html(result_frame, "14_result_frame")
            rows = result_frame.query_selector_all("table tr")
            print(f"  テーブル行数: {len(rows)}")
            for i, row in enumerate(rows[:30]):
                try:
                    text = row.inner_text().strip().replace("\n", " | ")
                    if text:
                        print(f"  行{i+1}: {text[:130]}")
                except Exception:
                    pass
            # リンクも確認
            links = result_frame.query_selector_all("a")
            print(f"\n  リンク ({len(links)} 件):")
            for lnk in links[:20]:
                try:
                    t = lnk.inner_text().strip()
                    h = lnk.get_attribute("href") or lnk.get_attribute("onclick") or ""
                    if t:
                        print(f"    [{t[:50]}] -> {h[:80]}")
                except Exception:
                    pass
        else:
            print("  [警告] 結果フレームが見つからず")

        print("\n完了。Enter で閉じる")
        input()
        browser.close()

if __name__ == "__main__":
    main()
