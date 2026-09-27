# Issue #16 実機確認手順書: キー・Clipboard・UI 部品・ブラウザの観測

## 1. 目的
Windows 実機環境において、キー入力（打鍵数と継続時間のみ、文字内容なし）、クリップボード操作（Copy/Paste のペアおよび形式・長さのみ、本文なし）、パスワード欄判定（打鍵数 0）、および UI 部品（ControlType・AutomationId のみ、Name・Value・TextPattern なし）が正しく観測・無害化されて FlowLens 中核（`Recorder`）へ渡されることを確認する。

## 2. 前提条件
- OS: Windows 10 または Windows 11
- Python 3.12 環境（`uiautomation`, `pywin32`, `psutil` 等）
- Google Chrome または Microsoft Edge、およびテキストエディタ（Notepad 等）

## 3. 確認手順

### ステップ 1: 入力・クリップボード監視の起動
PowerShell またはコマンドプロンプトで以下の監視テストスクリプトを実行します。

```powershell
$env:PYTHONPATH = "src"
python -c "
import time
from flowlens.core import Recorder, TimeRange
from flowlens.windows import WindowsActivityWatcher, WindowsInputWatcher

recorder = Recorder(storage_dir='manual_test_input_data')
act_watcher = WindowsActivityWatcher(recorder=recorder, poll_interval=1.0)
input_watcher = WindowsInputWatcher(recorder=recorder, poll_interval=0.5)

act_watcher.start()
input_watcher.start()
print('=== 監視を開始しました (Ctrl+C で終了) ===')
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    input_watcher.stop()
    act_watcher.stop()
    recorder.flush()
    export_path = recorder.export(
        time_range=TimeRange.all_time(),
        password='testpassword',
        destination='manual_test_input_export.zip'
    )
    print(f'エクスポート完了: {export_path}')
"
```

### ステップ 2: 通常の文字入力のテスト
1. メモ帳（Notepad）を開く。
2. メモ帳に「ConfidentialPassword123」とタイピングする。
3. Enter キーを押下する。

### ステップ 3: クリップボード転記のテスト（Chrome → Notepad）
1. Google Chrome を開き、適当なウェブページ（または検索窓）を開く。
2. テキストを選択して `Ctrl + C` を押す。
3. メモ帳にフォーカスを移し、`Ctrl + V` を押す。

### ステップ 4: パスワード欄入力のテスト
1. ブラウザのログイン画面（または Windows の認証ダイアログ/パスワード入力欄）にフォーカスを当てる。
2. パスワード欄に任意の文字列を入力する。

### ステップ 5: 監視の停止とデータ書き出し
コンソールで `Ctrl + C` を入力して監視を停止し、暗号化アーカイブ（`manual_test_input_export.zip`）を出力させる。

### ステップ 6: 記録内容の検証
1. 出力された `manual_test_input_export.zip` を解凍する。
2. `data.sqlite` を SQLite ビューアーで開き、各テーブルを確認する:
   - `typing_activities`:
     - メモ帳でのタイピングに対して `keystroke_count > 0` のレコードが存在すること。
     - 入力した具体的な文字（「ConfidentialPassword123」等）の列が存在せず、保存されていないこと。
     - パスワード欄でのタイピングレコードが存在する場合、`is_password = 1` かつ `keystroke_count = 0` であること。
   - `clipboard_transfers`:
     - `source_app` が `chrome.exe`、`target_app` が `notepad.exe` の転記レコードが記録されていること。
     - コピーした文章の中身の列が存在せず、保存されていないこと。
   - `control_events`:
     - 部品の `control_type`, `automation_id`, `class_name` は記録されているが、`Name` や `Value` の列が存在しないこと。
3. 書き出された SQLite ファイル全体をバイナリ検索し、「ConfidentialPassword123」やコピーした本文の文字列が一切含まれていないことを確認する。

## 4. 判定基準（合格条件）
- [ ] 文字入力に対して打鍵数のみが記録され、入力文字自体が一切残っていないこと。
- [ ] Chrome からメモ帳へのコピー＆貼り付けが Clipboard Transfer（1件）として記録され、クリップボード本文が一切残っていないこと。
- [ ] パスワード欄での入力時に `keystroke_count = 0` として記録されていること。
- [ ] ソースコード上に Enter 時にテキスト値を取得する処理や TextPattern/ValuePattern を永続化する処理が存在しないこと。
