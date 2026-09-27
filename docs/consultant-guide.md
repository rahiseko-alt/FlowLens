# FlowLens コンサルタント向け分析手順書

社員から受け取った診断データ（暗号化された1つの ZIP ファイル）を開き、Claude Code で分析するまでの手順です。開発者がいなくても同じ手順で再現できるように書いています。

## 1. 開く

- AES-256 で暗号化されているため、Windows の標準機能では開けません。**7-Zip** を入れてください。
- パスワードは社員から、ファイルとは別の方法（電話・別のメールなど）で受け取ります。

```bash
7z x FlowLens診断データ_20260927.zip -p"受け取ったパスワード" -o./analysis
```

中身は次の5つです。

| ファイル | 中身 |
| --- | --- |
| `data.sqlite` | 期間内のすべての記録 |
| `manifest.json` | 期間、機器 ID（ランダム。PC 名や氏名ではない）、表ごとの件数、版 |
| `summary.json` | プログラムだけで計算した集計（AI は使っていない） |
| `redaction_report.json` | 書き出し時に除いた件数（除外アプリ、パスワード欄など） |
| `README.txt` | 英語の要約（Claude Code にそのまま読ませてよい） |

## 2. データの読み方

### 前提

- **中身は入っていません。** 入力した文字、コピーした内容、画面、パスワード、URL の続きはありません。
- **ウィンドウの題名とファイル名は記号です**（16文字の英数字）。同じ記号は同じ題名を指しますが、元には戻せません。中身は報告会で社員に聞きます。拡張子（`.xlsx` など）だけは分かります。
- **時刻はすべて UTC です。** 日本時間は +9時間です。
- **`is_past` で2種類に分かれます。混ぜて数えないでください。**
  - `0` = 記録分（同意した後の記録。細かい）
  - `1` = 過去分（同意した時点で読み込んだ、過去30日分の粗い足跡）

### 記録分（`is_past = 0`）

| 表 | 1行の意味 | 主な列 |
| --- | --- | --- |
| `app_sessions` | 1つのアプリ（題名）が前面にあった一続きの時間。離席・ロック・スリープは含まない。題名が変わると別の行になる（アプリを切り替えた回数は `summary.json` の `foreground_switches`） | `app_name`, `title_symbol`, `title_ext`, `start_time`, `end_time`, `duration_seconds` |
| `typing_activities` | 入力のひとまとまり（2秒以上止まると区切る） | `app_name`, `title_symbol`, `keystroke_count`, `duration_seconds`, `is_password` |
| `operation_events` | 操作キー | `operation_type`（`ctrl+c` `ctrl+x` `ctrl+v` `enter` `tab` `escape` `shortcut`） |
| `clipboard_transfers` | コピー（切り取り）から貼り付けまでの1回 | `source_app`, `target_app`（空 = 貼り付けを検出できず）, `data_type`, `data_length` |
| `control_events` | クリック・フォーカスした UI 部品、ブラウザで開いたサイト | `event_type`（`click` `focus` `navigate`）, `control_type`, `automation_id`, `browser_domain` |
| `excluded_intervals` | 記録しなかった時間 | `reason`（`pause` = 一時停止, `excluded_app` = 記録しないアプリ） |

### 過去分（`is_past = 1`）

| 表 | 1行の意味 |
| --- | --- |
| `system_events` | PC の起動・終了・スリープ・復帰（とロック等。管理者権限があった場合のみ） |
| `past_app_stats` | アプリごとの累計（起動回数、前面にあった合計秒数、最後に使った時刻）。**30日分ではなく、PC に入ってからの累計**なので、比率として使う |
| `file_events` | 開いたファイル（記号と拡張子）と時刻 |
| `browser_events` | 訪れたサイト名（ドメイン）と時刻 |
| `past_import_runs` | 読み込み元ごとの結果（`success` / `failed` と理由コード） |

## 3. Claude Code での分析

全記録をそのまま渡さず、次の順で問いかけます。

1. **全体像**: 「`summary.json` と `manifest.json` を読んで、期間、記録された時間、よく使うアプリの上位を表にして」
2. **過去分での目星**（入れてすぐの提案用）: 「`past_app_stats` と `file_events` と `browser_events` から、よく使うアプリ、よく開く拡張子、毎日のように訪れるサイトを挙げて。数字は SQL で出し、推測は推測と書いて」
3. **流れの発見**（記録分）: 「`app_sessions` を時刻順に並べ、同じアプリの移り変わり（例: Outlook → Chrome → Excel）が何回繰り返されているか、曜日と時間帯つきで数えて」
4. **転記の発見**: 「`clipboard_transfers` で、どのアプリからどのアプリへの転記が多いか。貼り付け時刻（`paste_time`）に前面にあった `app_sessions` の `title_symbol` と突き合わせて、同じ画面への転記が繰り返されていないか」
5. **候補の評価**: 「上の結果から、自動化の候補を効果の大きい順に3〜5件。回数×1回の時間で月あたりの時間を出し、推定値であることを明記して」

注意:

- 数字は必ず SQL で出させ、AI に数字を作らせないでください。
- `title_symbol` が何の画面かは分かりません。「記号 A の Excel ファイル」のように書き、報告会で社員に確認する質問の一覧を作らせてください。

## 4. 報告会で確かめること

- 候補ごとに、記号の画面・ファイルが何か（例: 「毎朝9時に開く Excel ファイル A は何の表ですか」）
- その作業の目的、例外の多さ、判断が要る部分
