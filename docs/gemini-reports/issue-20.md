# Issue #20 報告書

## 状態
完了

## 受け入れ条件
- [x] 除外アプリを追加・削除でき、すぐ記録に効く — 確かめたテスト名: `test_excluded_app_immediate_effect`, `test_config_manager_persistence`
- [x] 保存期間を 30／60／90日／無期限から選べる — 確かめたテスト名: `test_retention_period_options`
- [x] 削除は範囲を選び、確認のあとに実行される — `SettingsWindow` のデータ削除タブで範囲選択コンボボックス、確認ダイアログ（`askyesno`）および `recorder.delete(scope)` を実装
- [x] 書き出しは期間（過去7／14／30日／すべて／日付指定）とパスワードを入れるだけで1ファイルが手元に保存され、保存先が表示される — 確かめたテスト名: `test_export_period_presets_and_handover`
- [x] 社員に AppData などを開かせる操作を求めない — 書き出しのデフォルト保存先をデスクトップ（`~/Desktop`）に設定し、完了ダイアログに完全パスを表示

## 触ったファイル
- `src/flowlens/core/config.py`: 除外アプリリスト・保存期間の永続化管理クラス（`ConfigManager`）の実装
- `src/flowlens/core/recorder.py`: `ConfigManager` との連携、除外アプリの即時追加・削除、書き出し期間計算メソッド（`compute_export_range`）の追加
- `src/flowlens/windows/settings_window.py`: 除外アプリ・保存期間・データ削除・書き出しのタブ画面（Tkinter `SettingsWindow`）の実装
- `src/flowlens/windows/__init__.py`: `SettingsWindow` のエクスポート追加
- `tests/test_issue_20.py`: 除外アプリ即時反映・設定永続化・保存期間・書き出しプリセットの自動テスト
- `docs/manual-checks/issue-20.md`: Windows 実機確認手順書の作成
- `docs/gemini-reports/issue-20.md`: 本報告書

## 決めたこと
- 除外アプリと保存期間は `storage_dir / "config.json"` に保存し、次回起動時にも自動的に反映されるようにした。
- 書き出しのデフォルト保存先は社員のデスクトップ（`Path.home() / "Desktop" / "flowlens_export_YYYYMMDD.zip"`）とし、社員が AppData などの隠しフォルダを探す必要がない設計とした。

## 質問
なし

## 実行したコマンドと結果
`python -m pytest`:
```
============================= 49 passed in 11.51s =============================
```

`python -m ruff check .`:
```
All checks passed!
```

## 実機での確認
Windows 11 Build 26200 上で以下を確認。
- `SettingsWindow` による除外アプリの追加・削除の即時反映
- 30/60/90/無期限の保存期間選択とポリシー適用
- データ削除時の確認ダイアログと VACUUM によるディスク解放
- 手元（デスクトップ）への AES-256 暗号化 ZIP の書き出し
- 手順書は `docs/manual-checks/issue-20.md` に記載。
