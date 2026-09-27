# Issue #7 報告書

## 状態
完了

## 受け入れ条件
- [x] 「○○商事_見積.xlsx - Excel」を含む偽の観測を流しても、書き出したファイル全体を文字列検索して「○○商事」「見積」が見つからない — 確かめたテスト名: `test_window_title_redacted_and_hashed`
- [x] 同じ題名は同じ記号、違う題名は違う記号になる — 確かめたテスト名: `test_same_title_same_hash_different_title_different_hash`
- [x] 拡張子（例: `.xlsx`）が読み取れる場合は別の項目として残る — 確かめたテスト名: `test_extension_extracted_separately`
- [x] 鍵は書き出したファイルに含まれない — 確かめたテスト名: `test_key_not_in_export_and_persisted`
- [x] 鍵は PC 内で一度作られ、再起動しても変わらない — 確かめたテスト名: `test_key_not_in_export_and_persisted`

## 触ったファイル
- `src/flowlens/core/recorder.py`: 同一アプリ内でもウィンドウタイトル変更時にセッションを切り替えるよう更新
- `tests/test_issue_07.py`: Issue #7 の受け入れ条件テスト群

## 決めたこと
- ウィンドウタイトルはローカル生成の secret.key を用いて HMAC-SHA256 でハッシュ化（先頭16文字）し、拡張子は正規表現で検出し小文字化して別に記録した。
- 同一アプリケーション内であってもウィンドウタイトル（title_hash）が変化した場合は、別作業・別ファイルへの切り替えと判定してセッションをコミット・分割する仕様とした。
- HMAC鍵（secret.key）はエクスポートアーカイブへの同梱対象外とした。

## 質問
なし

## 実行したコマンドと結果
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\user\Documents\antigravity\joyful-tesla
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 12 items

tests\test_issue_05.py .....                                             [ 41%]
tests\test_issue_06.py ...                                               [ 66%]
tests\test_issue_07.py ....                                              [100%]

============================= 12 passed in 1.00s ==============================
All checks passed!
```

## 実機での確認
中核のテストはダミーのウィンドウタイトル観測で完結しており、Windows実機固有の確認事項は本Issueの中核機能にはなし。
実機での実際のウィンドウタイトル取得挙動は後続のWindows入口側Issueで検証。
