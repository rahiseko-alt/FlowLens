# Issue #15 実機確認手順書: 前面アプリ・idle・ロック・スリープの観測

## 1. 目的
Windows 実機環境において、前面ウィンドウの切り替え（Chrome → Excel → Outlook 等）、idle（無操作離席）、Windows ロック（Win+L）、およびスリープ状態が `WindowsActivityWatcher` によって正しく検出され、FlowLens 中核（`Recorder`）へ観測として伝達されることを確認する。
また、ロックやスリープを挟んだ際にその時間が App Session に計上されず、ウィンドウタイトルの生の文字列が保存されないことを確認する。

## 2. 前提条件
- OS: Windows 10 または Windows 11
- Python 3.12 環境（依存関係: `pywin32`, `psutil`, `pyzipper` 等がインストール済み）

## 3. 確認手順

### ステップ 1: 監視スクリプトの準備と起動
PowerShell またはコマンドプロンプトで以下のテストスクリプトを実行し、常駐監視を開始します。

```powershell
$env:PYTHONPATH = "src"
python -c "
import time, tempfile
from pathlib import Path
from flowlens.core import Recorder, TimeRange
from flowlens.windows import WindowsActivityWatcher

recorder = Recorder(storage_dir='manual_test_data')
watcher = WindowsActivityWatcher(recorder=recorder, poll_interval=1.0, idle_threshold_seconds=60.0)
watcher.start()
print('=== 監視を開始しました (Ctrl+C で終了) ===')
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    watcher.stop()
    recorder.flush()
    export_path = recorder.export(
        time_range=TimeRange.all_time(),
        password='testpassword',
        destination='manual_test_export.zip'
    )
    print(f'エクスポート完了: {export_path}')
"
```

### ステップ 2: アプリケーションの切り替え
1. Google Chrome を最前面にして約10秒間操作（スクロール等）する。
2. Microsoft Excel（または任意の表計算・エディタ）を最前面にして約10秒間操作する。
3. Microsoft Outlook（または別のアドレス帳/メールアプリ）を最前面にして約10秒間操作する。

### ステップ 3: 画面ロックの挟み込み
1. キーボードで `Win + L` を押下して Windows をロックする。
2. ロック画面のまま約30秒間待機する。
3. パスワード/PINを入力してロックを解除し、デスクトップに戻る。
4. 再び Chrome を前面にして約10秒間操作する。

### ステップ 4: 監視の停止とデータ書き出し
コンソールで `Ctrl + C` を入力して監視を停止し、暗号化アーカイブ（`manual_test_export.zip`）を出力させる。

### ステップ 5: 記録内容の検証
1. 出力された `manual_test_export.zip` を 7-Zip 等で開き、パスワード `testpassword` で解凍する。
2. 解凍された `data.sqlite` を SQLite ビューアー（または Python）で開く。
3. 次の SQL を実行してセッション記録を確認する:
   ```sql
   SELECT app_name, window_title_hash, window_title_ext, start_time, end_time, duration_seconds
   FROM app_sessions
   ORDER BY start_time ASC;
   ```

## 4. 判定基準（合格条件）
- [ ] 前面にしたアプリ（`chrome.exe` → `excel.exe` → `outlook.exe` 等）がその順序で `app_sessions` に記録されていること。
- [ ] ウィンドウタイトルが生の文字列ではなく、ハッシュ値（`window_title_hash`）と拡張子（`window_title_ext`）のみになっていること。
- [ ] 画面ロック中の約30秒間が作業時間（`duration_seconds`）に加算されておらず、ロックの前後でセッションが適切に分割または終了していること。
- [ ] データベースおよび書き出しファイル全体を grep 検索しても、作業中のウィンドウタイトルの生文字列が見つからないこと。
