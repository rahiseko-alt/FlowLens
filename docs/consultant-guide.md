# FlowLens コンサルタント向け分析手順書

本書は、FlowLens Collector が出力した診断データ（AES-256 暗号化 ZIP）を受け取ったコンサルタントが、開発者の手を借りずに 7-Zip で展開し、データ構造を理解して Claude Code と協調しながら業務改善・自動化候補の分析を行うための手順書です。

---

## 1. 7-Zip での展開手順

FlowLens の書き出しファイル（例: `flowlens_export_20260927.zip`）は、**AES-256** で暗号化されています。Windows 標準のエクスプローラーでは暗号化方式（WinZip AES）に対応していない場合があるため、必ず **7-Zip**（または同等の AES-256 対応アーカイブツール）を使用してください。

### GUI 操作
1. 7-Zip File Manager を開くか、ZIP ファイルを右クリックして「7-Zip」→「ここに展開」または「展開...」を選択します。
2. パスワード入力ダイアログが表示されたら、社員本人から受領したパスワードを入力します。
3. 展開先に以下の5ファイルが生成されたことを確認します。
   - `data.sqlite`
   - `manifest.json`
   - `summary.json`
   - `redaction_report.json`
   - `README.txt`

### コマンドライン操作
```bash
7z x flowlens_export_20260927.zip -p"受領したパスワード" -o./analysis_dir
```

---

## 2. 同梱ファイルの意味と構成

| ファイル名 | 概要 |
| --- | --- |
| `manifest.json` | 収集バージョン、書き出し時刻、対象期間、機器ID、記録セッション数のメタデータ |
| `summary.json` | アプリ別使用時間、セッション数、クリップボード転送数の事前集計（live と past に分離） |
| `redaction_report.json` | 除外アプリ設定等により収集・書き出し時に除外・墨消しされた件数の監査ログ |
| `README.txt` | アーカイブ概要、プライバシー方針、展開手順の要約 |
| `data.sqlite` | SQLite データベース本体（WAL チェックポイント済み） |

### `data.sqlite` の主要テーブル

すべてのテーブルは `is_past`（0: 記録分、1: 過去分）および `source` 列を持ち、データの由来を完全に追跡できます。

1. **`app_sessions`**: アプリケーションの利用区間
   - `app_name`: プロセス名（例: `EXCEL.EXE`, `chrome.exe`）
   - `window_title_hash`: ウィンドウタイトルの HMAC-SHA256 ハッシュ値（記号化）
   - `window_title_ext`: ファイル拡張子（例: `.xlsx`, `.pdf`）
   - `start_time` / `end_time`: 開始・終了日時（ISO 8601 UTC）
   - `duration_seconds`: 使用秒数（アイドル・離席時間を除外した実稼働時間）
   - `is_past`: 0（記録分）または 1（過去分）
   - `source`: `live`, `user_assist`, `srum` など

2. **`typing_activities`**: 打鍵活動の集計（※入力文字は保存されません）
   - `app_name`, `window_title_hash`: 打鍵が行われたアプリ・文書
   - `keystroke_count`: 打鍵数
   - `duration_seconds`: 打鍵継続秒数
   - `is_password`: パスワード欄での打鍵であった場合 1（打鍵数は 0 に無害化）

3. **`clipboard_transfers`**: アプリ間のデータ受け渡し（※コピー本文は保存されません）
   - `source_app`: コピー元アプリ（例: `chrome.exe`）
   - `target_app`: ペースト先アプリ（例: `EXCEL.EXE`）
   - `data_type`: `text`, `image` 等の種別
   - `data_length`: データ長（文字数またはバイト数）
   - `copy_time` / `paste_time`: コピー日時とペースト日時

4. **`control_events`**: 操作された UI コントロール種別（※テキストや値は保存されません）
   - `control_type`: `Button`, `Edit`, `MenuItem` などの種別
   - `automation_id`, `class_name`: コントロールの識別子
   - `state`: コントロールの状態（`Focused`, `Invoked` 等）

5. **`system_events`**: PC 本体の電源・稼働イベント
   - `event_type`: `boot`, `shutdown`, `sleep`, `resume`, `lock`, `unlock` 等
   - `timestamp`: イベント発生時刻

6. **`file_events`**: 開かれたファイル足跡
   - `app_name`: 開いたアプリ（例: `WINWORD.EXE`）
   - `file_hash`: ファイルパスの HMAC-SHA256 ハッシュ値
   - `file_ext`: ファイル拡張子（例: `.docx`）
   - `timestamp`: 開いた時刻

7. **`browser_events`**: 閲覧履歴のドメイン足跡（※URL パス・クエリは保存されません）
   - `browser_domain`: 訪問ドメイン名（例: `salesforce.com`, `admin.internal`）
   - `timestamp`: 訪問時刻

---

## 3. プライバシー記号（ハッシュ値）の解釈とヒアリング方法

FlowLens は最小データ原則（ADR 0002・0003）に基づき、ウィンドウタイトルやファイルパスの生の文字列を一切記録しません。
PC 内の固有鍵による HMAC-SHA256 ハッシュ値（例: `e3b0c442...`）と拡張子（例: `.xlsx`）のみを保存します。

### ハッシュ値の読み方
- **同一のハッシュ値は同一の文書・画面を意味します。**
- 例えば、`app_name = 'EXCEL.EXE'` かつ `window_title_hash = '8f3a...'` が毎日 10:00〜10:30 に現れる場合、「毎日同じ特定の Excel 帳票を開いて 30 分作業している」ことが分かります。

### 社員ヒアリングでの確認方法
- 分析段階では、ハッシュ値を無理に復号しようとする必要はありません（復号キーは PC から持ち出されません）。
- 報告会や社員へのヒアリング時に、以下の情報を示して確認します:
  > 「Excel で拡張子 `.xlsx` のファイル（ハッシュ: `8f3a...`）を毎朝 10 時頃に開いて、その後ブラウザの `portal.example.com` へコピー＆ペーストされている流れが見られます。この帳票で行われているのはどのような業務でしょうか？」
- これにより、社員側も「勝手にファイルの中身を見られていない」という安心感を持って業務内容を答えることができます。

---

## 4. 過去分（Past Import）と記録分（Live Capture）の違い

分析にあたっては、両者の**粒度（解像度）の違い**を踏まえる必要があります。

| 項目 | 記録分（Live Capture: `is_past = 0`） | 過去分（Past Import: `is_past = 1`） |
| --- | --- | --- |
| **時間解像度** | 秒単位（1秒ポーリング・正確な前面滞在時間） | アプリごと・日ごとの累積時間や最終使用時刻 |
| **操作の詳細** | 打鍵数、コピー＆ペーストの転送元・先、UI部品種別 | なし（開いた事実・起動履歴のみ） |
| **主な用途** | 繰り返し操作パターン（UIフロー、転送フロー）の発見 | 過去30日間の業務アプリ構成、利用頻度、全体傾向の把握 |
| **価値** | 自動化スクリプトやマクロ化の設計材料 | **導入後 3 日で最初の改善提案を行うための即効性ある材料** |

---

## 5. Claude Code への渡し方と分析プロンプト例

### 注意: 全記録をそのまま Claude Code に渡さないこと
`data.sqlite` には数万〜数十万件のイベントが含まれるため、全データをテキストダンプして Claude Code に投入するとコンテキスト制限を超過し、分析の精度が著しく低下します。

**分析の推奨フロー:**
1. まず `summary.json` を Claude Code に読み込ませて全体像を把握する。
2. 次に、関心のあるテーマに応じた集計 SQL を `data.sqlite` に対して実行し、その集約結果テーブルを Claude Code に渡す。

### Claude Code への最初の問いかけ例

#### 問い 1: 全体像の把握（`summary.json` の分析）
```text
FlowLens Collector で収集した業務活動の集計データ summary.json を確認してください。
社員が最も多くの時間を費やしている上位 5 アプリケーションと、
過去分（past）と記録分（live）の利用比率を教えてください。
また、アプリ間でのクリップボード転送回数が多いペアを挙げてください。
```

#### 問い 2: ルーティン業務・繰り返し作業の発見（SQL 結果の分析）
以下の Python ワンライナーまたは sqlite3 コマンドでアプリ遷移頻度を集計し、その結果を Claude Code に渡します。

```bash
python -c "import sqlite3; conn = sqlite3.connect('data.sqlite'); cur = conn.cursor(); cur.execute('''
SELECT source_app, target_app, COUNT(*) as transfer_count, SUM(data_length) as total_chars
FROM clipboard_transfers WHERE is_past = 0
GROUP BY source_app, target_app ORDER BY transfer_count DESC LIMIT 10
'''); print(cur.fetchall())"
```

Claude Code へのプロンプト:
```text
上記のデータは、社員がアプリ間でコピー＆ペーストを行った回数と文字数の上位 10 件です。
この結果から、どのような定型転記作業や手動データ移行の可能性があるか仮説を立ててください。
また、ヒアリングで確認すべき具体的な業務シナリオを提案してください。
```

#### 問い 3: 定期的に開かれる文書・業務パターンの特定
```bash
python -c "import sqlite3; conn = sqlite3.connect('data.sqlite'); cur = conn.cursor(); cur.execute('''
SELECT app_name, window_title_ext, window_title_hash, COUNT(*) as session_count, ROUND(SUM(duration_seconds)/60, 1) as total_minutes
FROM app_sessions
WHERE window_title_ext != ''
GROUP BY app_name, window_title_hash
HAVING session_count >= 3
ORDER BY total_minutes DESC LIMIT 10
'''); print(cur.fetchall())"
```

Claude Code へのプロンプト:
```text
上記は複数回繰り返し開かれている同一文書（ハッシュ単位）の利用時間上位リストです。
業務改善の優先度が高い文書クラスターを選定し、社員ヒアリング用の質問票を作成してください。
```
