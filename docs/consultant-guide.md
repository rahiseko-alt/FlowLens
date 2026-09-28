# FlowLens コンサルタント向け分析手順書

社員から受け取った診断データ（暗号化された1つの ZIP ファイル）を分析コマンドにかけ、Claude Code でご提案書を書くまでの手順です。開発者がいなくても同じ手順で再現できるように書いています。

## 1. 分析コマンドで要約を作る

診断データ（ZIP）を、FlowLens の分析コマンドに渡します。1社で複数の社員から受け取った場合は、まとめて渡してください。

```bash
python -m flowlens.analyst Aさん.zip Bさん.zip --out ./analysis
```

- パスワードはファイルごとに尋ねられます（画面には表示されません）。社員から、ファイルとは別の方法（電話・別のメールなど）で受け取ってください。
- 読めないファイル（パスワード違い、壊れている、版が違う）があると、ファイル名と理由を出して止まります。
- 集計は日本時間で行います。別の地域なら `--tz` で変えます（例: `--tz UTC`）。
- 「繰り返し」とみなす基準は、既定で「2日以上にわたり合計3回以上」です。データが少ないときは `--min-days` と `--min-count` で変えて、もう一度実行します。
- 同じ社員の期間の重なる書き出しを2つ渡しても、二重には数えません。

`./analysis` には、毎回次の4つができます。

| ファイル | 中身 | AI に渡すか |
| --- | --- | --- |
| `analysis_summary.json` | プログラムが数えた要約（Analysis Summary）。元の記録の行、記号、機器 ID は入っていない | 渡す |
| `confirmation_questions.md` | 報告会で社員に聞く質問の下書き（確認リスト） | 渡す |
| `instructions_for_claude.md` | Claude Code への指示書 | 渡す |
| `do_not_send_to_ai/labels.json` | 「ファイル A」などの呼び名と記号の対応表 | **渡さない** |

中身を直接確かめたいときは、7-Zip で ZIP を開けます（AES-256 のため Windows の標準機能では開けません）。

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

`./analysis` フォルダで Claude Code を開き、次のように頼みます。

> `instructions_for_claude.md` に従って、ご提案書を書いてください。

- 指示書に、読むのは要約と確認リストだけ、数字は要約の値だけを使う、推定は推定と書く、個人を比べない、と書いてあります。
- `do_not_send_to_ai` フォルダは AI に読ませないでください。報告会で答えを聞いたあと、呼び名を記号に結び付けるときにだけ使います。
- 元の記録（下の表）を AI に丸ごと読ませないでください（`docs/adr/0006-analysis-counts-first-ai-reads-summary.md`）。2 の表は、コンサルタントが中身を確かめるときの参考です。

## 4. 報告会で確かめること

`confirmation_questions.md` の質問をもとに伺います。答えは、`do_not_send_to_ai/labels.json` の呼び名と記号の対応で記録に結び付けられます。

- 候補ごとに、記号の画面・ファイルが何か（例: 「毎朝9時に開く Excel ファイル A は何の表ですか」）
- その作業の目的、例外の多さ、判断が要る部分
