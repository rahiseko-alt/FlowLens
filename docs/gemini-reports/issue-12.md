# Issue #12 報告書

## 状態
完了

## 受け入れ条件
- [x] 範囲を指定して削除すると、その範囲の記録だけが消え、書き出したファイルにも現れない — 確かめたテスト名: `test_delete_by_range_and_scope`
- [x] 保存期間を過ぎた記録が自動削除で消える。無期限では消えない — 確かめたテスト名: `test_retention_policy_auto_delete`
- [x] 削除は外部キーなどで途中で止まらない（DeskMate で起きた不具合を繰り返さない） — 確かめたテスト名: `test_deletion_does_not_fail_with_foreign_keys`
- [x] 削除後にデータ使用量が減る — 確かめたテスト名: `test_database_size_decreases_after_deletion`

## 触ったファイル
- `src/flowlens/core/storage.py`: `delete_range` および `delete_before` メソッドの追加。全テーブルを網羅した削除処理と SQLite `VACUUM` / `wal_checkpoint(TRUNCATE)` によるディスク領域回収
- `src/flowlens/core/recorder.py`: `delete` メソッドの拡張（`TimeRange` および `'today'`, `'last_7_days'`, `'last_30_days'`, `'all'` のスコープ文字列対応）、保存期間設定 `set_retention_days`（無期限 `None` 対応）および `apply_retention_policy` の実装
- `tests/test_issue_12.py`: Issue #12 の受け入れ条件テスト群

## 決めたこと
- `Recorder.delete` は `TimeRange` インスタンスに加えて、UIから指定されるプリセット（`"today"`, `"last_7_days"`, `"last_30_days"`, `"all"`）をスコープ文字列として受け取れるようにした。
- 削除対象は `app_sessions`, `typing_activities`, `operation_types`, `clipboard_transfers`, `control_events`, `excluded_intervals` のすべての記録テーブルとし、外部キー制約に引っかかって削除が中断する DeskMate 類似の不具合を防止した。
- レコード削除後には自動的に `VACUUM` を実行し、SQLite データベースファイルの不要ページを回収して実ファイルサイズを縮小させる仕様とした。
- 保存期間（retention days）は初期値30日とし、`None` または `0` を設定した場合は無期限保持として自動削除の対象外とする。

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
collected 32 items

tests\test_issue_05.py .....                                             [ 15%]
tests\test_issue_06.py ...                                               [ 25%]
tests\test_issue_07.py ....                                              [ 37%]
tests\test_issue_08.py ....                                              [ 50%]
tests\test_issue_09.py ....                                              [ 62%]
tests\test_issue_10.py ....                                              [ 75%]
tests\test_issue_11.py ....                                              [ 87%]
tests\test_issue_12.py ....                                              [100%]

============================= 32 passed in 10.70s =============================
All checks passed!
```

## 実機での確認
中核のテストは `delete` と `apply_retention_policy` の動作、データベースファイル縮小の確認で完結。Windows実機固有の確認事項は本Issueの中核機能にはなし。
