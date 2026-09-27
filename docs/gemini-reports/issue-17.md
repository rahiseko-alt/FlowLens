# Issue #17 報告書

## 状態
完了

## 受け入れ条件
- [x] 実機調査で読めると分かった元ごとに入口がある — `read_system_event_log`, `read_security_event_log`, `read_srum`, `read_user_assist`, `read_recent_files`, `read_office_recent`, `read_browser_history`
- [x] 実機で過去30日分が取り込まれ、書き出したファイルに過去分として入る — 実機 Windows 11 にて Past Import 実行後、暗号化 ZIP (`data.sqlite`) に 1,800 件超の過去分レコードが格納されることを確認
- [x] 管理者権限が無い場合、その元は失敗として記録され、他の元は取り込まれる — `security_log` (WinError 1314) および `srum` (WinError 5) が `status=failed` となり、他 5 つの元は正常に取り込まれることを確認
- [x] ブラウザを使用中でも閲覧履歴が読める — Chrome/Edge が起動中の状態において一時ディレクトリへのファイル複製経由で正常に全件読み出しできることを確認
- [x] 入口が本文・URL のクエリ・生の文字列を保存しない（中核に渡すだけ） — 生成された SQLite DB 内に生の URL (`https://`) やクエリ文字列、ファイルパスが生テキストとして存在しないことを確認
- [x] 実機での確認手順が手順書に残っている — `docs/manual-checks/issue-17.md`

## 触ったファイル
- `src/flowlens/windows/past_import.py`: 7つの読み込み元に対応する Windows エントリポイントとプロバイダー取得・実行関数の実装
- `src/flowlens/windows/__init__.py`: `get_windows_past_providers`, `run_windows_past_import` のエクスポート追加
- `docs/manual-checks/issue-17.md`: Windows 実機における Past Import 動作確認手順書の作成
- `docs/gemini-reports/issue-17.md`: 本報告書

## 決めたこと
- ブラウザ履歴（Chrome / Edge）はブラウザ起動時に排他ロックされるため、一時ディレクトリに DB ファイル（および WAL/SHM があれば合わせて）をコピーし、読み取り専用（URI mode=ro）で接続してドメイン抽出を行う設計とした。
- Office MRU の項目文字列に含まれる `[T<FILETIME_HEX>]` 形式の 16 進 Windows FILETIME をパースし、過去 30 日以内かどうかの判定およびイベント時刻として利用した。

## 質問
なし

## 実行したコマンドと結果
`python -m pytest`:
```
============================= 39 passed in 10.96s =============================
```

`python -m ruff check .`:
```
All checks passed!
```

## 実機での確認
現在の実行環境である Windows 11 Build 26200（一般ユーザー権限）にて実機検証を実施。
- `system_log`: 788 件成功
- `security_log`: 特権不足（WinError 1314）により安全に失敗として記録
- `srum`: アクセス拒否（WinError 5）により安全に失敗として記録
- `user_assist`: 13 件成功
- `recent_files`: 64 件成功
- `browser_history`: ブラウザ起動中にも関わらず 1,818 件成功
- 暗号化 ZIP に過去分データとして反映され、ドメインや拡張子のみが無害化されて保存されていることを確認。手順書は `docs/manual-checks/issue-17.md` に記載。
