# Issue #17 実機確認手順書: Past Import の読み込み元（Windows 側）

この手順書は、Windows 実機において過去30日分の足跡（イベントログ、UserAssist、最近使ったファイル、Office MRU、ブラウザ閲覧履歴等）を読み込み、管理者権限がない元が安全にスキップされ、暗号化 ZIP 書き出しに含まれることを確認する手順です。

## 前提条件
- OS: Windows 10 または Windows 11
- Python: 3.12 (pywin32, pyzipper インストール済み)
- 実行権限: 一般ユーザー権限（非管理者権限）

## 確認手順

1. **Past Import の実行**
   Python 対話シェルまたはスクリプトで以下を実行します。

   ```python
   import tempfile, os, sqlite3
   from datetime import datetime, timedelta, timezone
   import pyzipper
   from flowlens.core import Recorder
   from flowlens.core.models import TimeRange
   from flowlens.windows import run_windows_past_import

   with tempfile.TemporaryDirectory() as td:
       recorder = Recorder(storage_dir=td)
       report = run_windows_past_import(recorder, max_days=30)

       print("=== Past Import 結果 ===")
       for src, res in report.items():
           print(f"{src}: status={res['status']}, count={res['count']}, error={res['error']}")

       # データベース確認
       db_path = os.path.join(td, "collector.db")
       conn = sqlite3.connect(db_path)
       cur = conn.cursor()
       for table in ["system_events", "file_events", "browser_events", "app_sessions"]:
           cur.execute(f"SELECT COUNT(*) FROM {table} WHERE is_past = 1")
           print(f"{table} (past):", cur.fetchone()[0])
       conn.close()

       # 書き出し確認
       zip_dest = os.path.join(td, "export.zip")
       now = datetime.now(timezone.utc)
       recorder.export(TimeRange(start=now - timedelta(days=30), end=now), password="test", destination=zip_dest)

       with pyzipper.AESZipFile(zip_dest) as zf:
           zf.setpassword(b"test")
           zf.extractall(path=td, members=["data.sqlite"])

       conn = sqlite3.connect(os.path.join(td, "data.sqlite"))
       cur = conn.cursor()
       cur.execute("SELECT COUNT(*) FROM browser_events WHERE is_past = 1")
       print("Exported past browser events:", cur.fetchone()[0])
       conn.close()
   ```

2. **確認ポイント**
   - [x] 一般権限実行時に、`security_log` および `srum` が `status=failed` となり適切なエラー（特権不足 / アクセス拒否）が記録されていること。
   - [x] 他の元（`system_log`、`user_assist`、`recent_files`、`browser_history` など）が `status=success` となり過去データが取り込まれていること。
   - [x] ブラウザ（Chrome / Edge）が起動中でも閲覧履歴がロックエラーにならず読み取れること（一時コピー経由）。
   - [x] 生成された SQLite および書き出し ZIP 内に URL の生クエリや本文・生のファイルパスが含まれず、ドメインや拡張子・ハッシュのみが無害化されて保存されていること。
