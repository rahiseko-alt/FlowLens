# Issue #18 実機確認手順書: 常駐アイコンと初回の同意画面

この手順書は、Windows 実機において FlowLens の初回同意画面、読み込み元選択、常駐・二重起動防止、状態表示画面、自動起動設定、およびログの無害化を確認する手順です。

## 前提条件
- OS: Windows 10 または Windows 11
- Python: 3.12 (Tkinter, pywin32 インストール済み)
- 実行権限: 一般ユーザー権限

## 確認手順

1. **初回同意画面の表示と元ごとの選択**
   以下を実行して同意画面を開きます。
   ```python
   from flowlens.windows.consent_dialog import ConsentDialog
   dialog = ConsentDialog()
   consented = dialog.show()
   print("Consented:", consented)
   print("Selected sources:", dialog.selected_sources)
   ```
   - [x] プライバシー保護の原則（PC内保存、AI・外部送信なし、文字は残らない、いつでも停止可能、過去30日分読むこと）が表示されること。
   - [x] 7つの元（システムログ、セキュリティログ、SRUM、UserAssist、最近使ったファイル、Office MRU、ブラウザ履歴）が初期状態で全てチェックされていること。
   - [x] 特定の元（例: ブラウザ履歴）のチェックを外して同意できること。
   - [x] 「同意しない（終了）」を選択すると何も保存・読み込みされずに終了すること。

2. **状態表示画面の確認**
   以下を実行して状態画面を開きます。
   ```python
   import tempfile
   from flowlens.core import Recorder
   from flowlens.windows.status_window import StatusWindow

   with tempfile.TemporaryDirectory() as td:
       recorder = Recorder(storage_dir=td)
       win = StatusWindow(recorder)
       win.show()
   ```
   - [x] 動作状態（● 記録中 / ⏸ 一時停止中）が表示されること。
   - [x] 収集開始日時、記録済み時間、データ使用量（MB/KB）が表示されること。
   - [x] 「一時停止」ボタンを押すと「再開」に切り替わり、状態が「⏸ 一時停止中」に変化すること。

3. **二重起動防止（SingleInstanceLock）**
   同一ストレージディレクトリに対して2つ目のインスタンスを起動し、`AlreadyRunningError` が発生して二重起動が防止されることを確認する。

4. **自動起動設定（Registry Run キー）**
   `flowlens.windows.autostart` の `set_autostart` / `is_autostart_enabled` により、HKCU Run キーに登録・削除できることを確認する。

5. **ログのプライバシー確認**
   `flowlens.log` を確認し、記録開始・同意・エラー等のライフサイクル情報のみが出力され、パスワード・URL・入力内容・ウィンドウタイトル本文が出力されていないことを確認する。
