# DeskMate 流用調査（2026-09-27）

- 対象: [zhaohb/deskmate](https://github.com/zhaohb/deskmate)（MIT）。調査時点の最新コミットは `6db6e0e`（2026-08-27）。
- 判定の基準: `docs/adr/0002-minimum-data-principle.md`（最小データ原則）。
- この文書は調査の記録であり、仕様ではない。ファイルと行の番号は上記コミット時点のもの。

## 要点

1. **本文を保存している経路が3本に限らない。** Enter を押したときの入力欄の値（`a11y/input_hooks.py:432-475`）と Clipboard 本文（`a11y/clipboard.py:69-99`）は `ui_events.data_json`、全文検索用の `ui_events_fts`、`context_events.summary`（最大200文字）の3か所に入る。これとは別に、UIA の画面テキストが `frame_accessibility` に入る。
2. **除外設定が UI 操作の記録に効いていない。** パスワード管理アプリの除外（`ignored_apps`）とシークレットウィンドウの判定は、スクリーンショットにしか適用されていない（`capture/paired.py:137-145`）。UI 操作の記録で適用されるのはウィンドウタイトルの除外だけ（`capture/ui_event_pipeline.py:127`）。そのため除外アプリの操作・タイトル・URL・Clipboard 本文は `ui_events` に入る。
3. **パスワード欄の判定が一部で常に「違う」を返す。** `_safe_is_password`（`a11y/uia_tree.py:755-758`）が、uiautomation ライブラリに存在しない属性 `CurrentIsPassword` を読んでいる。高速な読み取り経路（`IsPassword` を事前に取得する側）では正しく判定できる。
4. **自動的に消す仕組みが通常の使い方で失敗する。** `ui_events.frame_id` に削除時の扱いが定義されていないため、`cleanup()` が外部キー違反で止まる。調査役が実際に再現した。`ui_events` と `context_events` はそもそも削除の対象外。
5. **FlowLens が必要とする信号の多くが記録されていない。** 入力の回数、Paste、クリックした部品の種別、フォーカスの継続時間、idle（操作していない時間）、ロック、スリープ、ファイル操作がこれにあたる。

## 追加調査10項目の回答

1. **`uia_tree.py` が永続保存しているテキストの範囲**
   - Name、Value、HelpText などを取得している。ValuePattern で値が取れないときは TextPattern を使い、文書の本文を最大2000文字まで読み込み、1000文字で切って保存する。
   - 全部品の Name と Value をつなげた文字列（最大1万文字）が `frame_accessibility.text` に、部品の一覧がまるごと `frame_accessibility.tree_json` に保存される。
   - `tree_json` は、文字を伏せる設定を有効にしても伏せられない。その設定も初期状態では無効（`config.py:158`）。
2. **`browser_url.py` の URL の粒度**
   - アドレスバーの文字列を読んで、そのまま保存する。パス、クエリ文字列、フラグメントも含む。
   - 空白を含むもの（検索語）と、http / https 以外の URL だけを捨てている。無害化の処理は無い。
   - 保存先は `frames.browser_url` と `ui_events.browser_url`。`ui_events` 側には、クリックや Clipboard を含むすべての操作ごとに記録される。
3. **ウィンドウタイトルの保存方法**
   - `GetWindowTextW` で最大1024文字を読み、そのまま保存する。保存先は `frames.window_name`、`ui_events.window_title`、`context_events.window_title` と `summary`、全文検索用のテーブル。
   - 正規化やマスクはしていない。
4. **UIA の Name / Value の保存先**
   - `frame_accessibility`（text、tree_json、focused_name、focused_value）。
   - `elements`（name、value）と、その全文検索用テーブル。ただし `elements` への保存は初期状態で無効（`config.py:69`）。
   - FrameworkId はどこにも記録していない。ClassName と IsEnabled は `tree_json` にだけある。
5. **Clipboard の Paste を検出できるか**
   - できない。変化を1秒ごとに確かめて Copy を捉えるだけ。
   - `operation` は常に "c"（`a11y/ui_event_types.py:233`）。Ctrl+V の検出も、ソースのどこにも無い。
   - 元のアプリは、変化に気づいた時点の前面アプリで代用している。
6. **ファイル操作の監視があるか**
   - 無い。`a11y/document.py` は、エディタのウィンドウタイトルからファイル名を推定するだけ。
7. **idle / ロック / スリープ / 復帰の判定**
   - idle は `GetLastInputInfo` で測っているが、撮影の間隔を調整するのにしか使っていない。
   - ロック、スリープ、セッションの切断は扱っていない。
   - フォーカスの時間は、画面を撮った間隔から推定している。間隔が300秒未満なら使っていたとみなすため、最大299秒の離席が作業時間に数えられる。
8. **流用すべき SQLite のテーブル**
   - `ui_events`: 本文の列を外して、中心のテーブルにする。
   - `capture_control`: 一時停止の状態。そのまま流用する。
   - `_pca_migrations`: スキーマの版の管理。
   - `elements`: 考え方だけ流用する（ControlType と AutomationId を残し、name と value を外す）。
   - これ以外（全文検索、ベクトル、音声、会議、習慣、学習など）は流用しない。WAL などの接続設定は流用する。
9. **AI 機能を削除した場合の依存関係**
   - `engine/__init__.py:3` が REST サーバーを先に読み込むため、記録の本体（daemon）を読み込むだけで FastAPI、httpx、Pillow などがついてくる。
   - daemon が、学習、会議、習慣、アプリ実行、Ollama の自動起動を、設定に関係なく組み立てている（`engine/daemon.py`）。
   - そのため、部品を消すだけでは足りない。daemon を小さく書き直す必要がある。
10. **独立した EXE にするための最小の依存**
    - 必要なのは pydantic、pydantic-settings、pywin32、uiautomation（comtypes を含む）、psutil。
    - fastapi、uvicorn、anyio、typer、httpx、mss、Pillow、winrt 系は外せる。
    - 既存の配布の仕組み（PyInstaller などの設定）は無い。

## 5分類

### そのまま流用

- `a11y/win_events.py`: 前面ウィンドウの切り替えとフォーカスの監視。
- `a11y/recorder.py`: 監視役3つをまとめて起動する。
- `core/filter.py`、`core/incognito.py`: 除外判定。適用する範囲は、このあと広げる。
- `logger.py`、`console.py`: 標準ライブラリだけで書かれている。ログは5MB×3でローテーションする。
- `events.py`: 処理どうしの受け渡し役。
- `workflow/classifier.py`: Analyst 側で使う。外部へ問い合わせる経路は外す。

### 小変更で流用

- `a11y/uia_tree.py`、`a11y/uia_thread.py`: ControlType、AutomationId、ClassName、FrameworkId だけを読むようにする。Value と TextPattern は読まない。パスワード判定の不具合を直す。
- `a11y/activity_feed.py`: idle の時計を流用し、idle の開始と終了を記録する。
- `a11y/browser_url.py`: 読み取りの部分は流用し、ドメイン（必要ならパス）だけを残す処理を足す。
- `a11y/ui_event_types.py`: 本文の項目を外し、部品の種別などの項目を足す。
- `capture/ui_event_pipeline.py`: 除外判定を完全に適用する。撮影との連携と会議の検出への受け渡しを外す。
- `fusion/control.py`: 一時停止と再開の仕組み。撮影と音声の切り替えは外す。
- `paths.py`、`__init__.py`、`__main__.py`、`engine/__init__.py`: 名前、保存先、起動口を変える。

### 大幅変更

- `a11y/input_hooks.py`: Enter で入力欄の値を読む処理を削除する。入力の回数と継続時間（キーの種類は持たない）と、Ctrl+C / X / V などの操作の種類を足す。
- `a11y/clipboard.py`: 本文を読まず、種類・長さ・元のアプリだけを持つ。
- `config.py`: 使わない設定の節（15ほど）を外す。
- `db/schema.py`、`db/manager.py`: 小さなスキーマに作り直し、全文検索を外し、外部キーを直す。自動削除には `ui_events` も含める。
- `engine/daemon.py`: 監視役、記録の流れ、自動削除だけを動かす小さな本体に書き直す。
- `engine/cli.py`: REST と Web を外し、記録・一時停止・再開・書き出しだけにする。

### 削除

- 撮影と OCR: `screen/`、`capture/paired.py`、`capture/event_driven_capture.py`、`capture/frame_linker.py`、`capture/visual_change.py`。
- 文字を伏せる処理: `core/pii.py`、`redact/`。本文を持たないので不要になる。
- 検索: `db/search_engine.py`、`db/semantic_index.py`、`db/embeddings.py`、`db/search_types.py`、`db/text_normalizer.py`。
- `fusion/bus.py`: `ui_events` と重複し、本文を保存している。
- REST・LLM・実行予約: `engine/api.py`、`engine/ask.py`、`engine/llm.py`、`engine/jobs.py`、`engine/app_scheduler.py`、`engine/app_schedules.py`、`engine/doctor.py`、`engine/activity_summary.py`、`engine/day_recap_context.py`。
  - `activity_summary.py` の、アプリごとの時間を集計する SQL は、`summary.json` を作るときの参考にする。
- Web 画面: `ui/`。
- 音声と会議: `audio/`、`meeting/`。
- 習慣と学習: `habits/`、`learning/`、`learning_memory/`。
- アプリ群と外部連携: `apps/`、`pipes/`、`mcp/`、`connections/`、`modelsvc/`、`model_status.py`。
- 判断を保留: `platform/`（省電力の工夫。負荷を下げる目的で残す余地がある）、`a11y/document.py`（タイトルからファイル名を推定する。ファイル名を残す粒度が決まってから判断する）。

### 新規実装

- App Session の追跡: 前面にある期間の開始と終了。idle、ロック、スリープを除く。
- ロック、スリープ、セッション切断の検出。
- Typing Activity の集計: ウィンドウごと・時間ごとの回数。キーの種類は持たない。
- Clipboard Transfer の検出: Copy と Paste の組。
- 操作された UI 部品の Control Metadata を読む処理（クリックとフォーカスのとき）。
- ウィンドウタイトルとファイルパスの正規化・マスク。
- Diagnostic Export: 期間の指定、書き出し時の再無害化、`manifest.json`、`summary.json`、`redaction_report.json`、ZIP。
- 常駐アイコン、初回の説明画面、設定画面、除外設定の画面、データを削除する画面。
- 二重起動の防止、ログイン時の自動起動、止まった処理の再起動。
- 配布物の作成（インストーラーの形式は依存を確かめたうえで選ぶ）。
- 外部と通信していないことを確かめるテスト。

## 未確認

- UI 部品の Name について、固定の UI ラベルとユーザーが書いた内容を確実に見分けられるかは、調べていない。ADR 0002 に従い、MVP では保存しない側に倒す。
- 実際の Windows 機では何も動かしていない。調査はすべてコードを読んだ結果である（テストは Linux 上で18件が通った）。
