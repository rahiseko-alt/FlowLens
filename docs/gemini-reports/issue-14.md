# Issue #14 報告書

## 状態
完了

## 受け入れ条件
- [x] 過去分は記録分と区別され、読み込んだ元が分かる — 確かめたテスト名: `test_past_records_distinguished_and_sanitized`
- [x] ファイル名・題名は記号と拡張子になり、閲覧履歴はドメインだけになる（生の文字列を検索しても見つからない） — 確かめたテスト名: `test_past_records_distinguished_and_sanitized`
- [x] 選ばれていない元は読まれない — 確かめたテスト名: `test_unselected_sources_not_imported`
- [x] 1つの元が失敗しても他の元は取り込まれ、元ごとの件数と読めなかった理由が残る — 確かめたテスト名: `test_single_source_failure_does_not_block_others`
- [x] 後から追加で読み込んでも、既に取り込んだ分が二重にならない — 確かめたテスト名: `test_incremental_import_deduplication`
- [x] 除外アプリの過去分も除かれる — 確かめたテスト名: `test_excluded_app_and_older_than_30_days_filtered`
- [x] 過去30日より古い記録は取り込まない — 確かめたテスト名: `test_excluded_app_and_older_than_30_days_filtered`

## 触ったファイル
- `src/flowlens/core/models.py`: 過去記録データクラス（`PastAppUsageObservation`, `PastSystemEventObservation`, `PastFileObservation`, `PastBrowserObservation`）の追加
- `src/flowlens/core/__init__.py`: 上記モデルのエクスポート
- `src/flowlens/core/storage.py`: `system_events`, `file_events`, `browser_events` テーブルおよび重複排除用の一意インデックスの追加、`export_subset` と削除処理（`delete_range`, `delete_before`）の対応
- `src/flowlens/core/recorder.py`: `set_enabled_past_sources`, `is_past_source_enabled`, `import_past_records`, `import_past_providers` の実装（30日カットオフ、除外アプリフィルタ、題名/ファイル名ハッシュ化、URLドメイン抽出、重複排除、プロバイダ障害隔離）
- `tests/test_issue_14.py`: Issue #14 の受け入れ条件テスト群

## 決めたこと
- 過去記録としてアプリ使用履歴（SRUM/UserAssist等）、システム電源/セッション履歴（EventLog）、開いたファイル（Recent files/JumpList等）、閲覧履歴（Chrome/Edge等）の4種別を取り込めるようにした。
- 過去記録でも最小データ原則（ADR 0002, 0003, 0004）を厳格に適用し、ファイルパスやウィンドウタイトルはファイル名ベースで HMAC ハッシュと拡張子に変換し、ブラウザ履歴はドメインのみ抽出し、生のパスやトークンは一切保存しない。
- 読み込み元（`source`）は個別選択可能とし、選択されていない元の記録はスキップする。
- 複数プロバイダの一括取り込み（`import_past_providers`）では、個別プロバイダの例外（権限エラー等）を捕捉してレポートに記録し、他の健全なプロバイダの取り込みを中断させない。
- 過去30日（`clock() - 30 days`）を超える記録、および除外アプリリストに含まれるアプリの記録は自動的に除外する。
- 同一ソースから再度同一レコードを取り込んだ場合も、SQLite の一意制約および `INSERT OR IGNORE` により重複保存されないようにした。

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
collected 39 items

tests\test_issue_05.py .....                                             [ 12%]
tests\test_issue_06.py ...                                               [ 20%]
tests\test_issue_07.py ....                                              [ 30%]
tests\test_issue_08.py ....                                              [ 41%]
tests\test_issue_09.py ....                                              [ 51%]
tests\test_issue_10.py ....                                              [ 61%]
tests\test_issue_11.py ....                                              [ 71%]
tests\test_issue_12.py ....                                              [ 82%]
tests\test_issue_13.py ..                                                [ 87%]
tests\test_issue_14.py .....                                             [100%]

============================= 39 passed in 11.87s =============================
All checks passed!
```

## 実機での確認
中核のテストはダミーの過去レコードデータによる検証で完結。Windows実機のEventLog、レジストリ、ファイルシステムからの実データ読み込みはIssue #15で実施。
