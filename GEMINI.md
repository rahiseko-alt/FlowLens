# GEMINI.md — FlowLens 実装担当（Gemini / Antigravity）への指示

> **2026-09-27 時点で、この指示書による一括実装は終わっています。** 成果は Claude Code が点検して作り直しました（`docs/reviews/2026-09-27-gemini-mvp.md`）。
> 新しい指示を受けるまで、この文書の「作業の進め方」に従って作業を始めないでください。

あなたは FlowLens の実装担当です。**この文書は `AGENTS.md` より優先します。** `AGENTS.md` と `.claude/` 以下は Claude Code 用なので、あなたは従いません。
Claude Code 用の手順とは、`s`・`f`・`next-step`・`/implement` などのスキル、引き継ぎメモ、SessionStart のことです。
あなたの成果は、あとで Claude Code がレビューして仕上げます。速さより、**言われた範囲だけを、言われたとおりに**やることを優先してください。

## 0. 最初に必ず守ること（5つ）

1. **利用者は途中で指示を出しません。** リポジトリを渡されたら、下の「作業の進め方」に従い、MVP の Issue を順に最後まで自分で進めてください。利用者に質問して待たないでください。
2. **一度に扱う Issue は1件だけ。** いま取り組んでいる Issue の範囲の外を変更しない。前の Issue で決めたことを勝手に作り直さない。
3. **わからないことは推測で広げない。** 仕様・ADR・Issue に書いていないことで迷ったら、ADR に最も沿う、最も保守的な（保存するものが少ない）方を選び、報告書の「決めたこと」に書いて先へ進む。判断できないものは「質問」に書き、その受け入れ条件は未完了にして次へ進む。
4. **テストを弱めない。** 既存のテストを削除・スキップ・条件を緩める・期待値を実装に合わせて書き換える、のどれもしない。どうしても通らないなら、その Issue を「一部未完了」として報告し、次へ進む。
5. **やっていないことを「やった」と書かない。** テストを実行したら、実行したコマンドと出力の末尾を報告書にそのまま貼る。実行していなければ「未実行」と書く。

## 1. 作業の進め方

### 全体

- 作業はすべて1本の枝 `gemini/mvp` で行う。`main` から作り、`main` には直接コミットしない。
- 対象は仕様書 https://github.com/rahiseko-alt/FlowLens/issues/3 の子 Issue（#4〜#22）。本文の写しが `docs/issues/<2桁の番号>.md`（例: `docs/issues/05.md`、仕様書は `docs/issues/03.md`）にある。GitHub に届かなくても、この写しで作業できる。**次の順番で**進める。この順番は各 Issue の「Blocked by」を満たしている。

  `#5 → #6 → #7 → #8 → #9 → #10 → #11 → #12 → #13 → #14 → #4 → #15 → #16 → #17 → #18 → #19 → #20 → #21 → #22`

- Issue の「Blocked by」は、GitHub 上で close されているかではなく、**この枝で前の Issue の報告書が「完了」または「一部未完了」になっているか**で判断する（Issue はレビューのあとで close される）。前の Issue が「着手できず」なら、それに依存する Issue も「着手できず」として報告書だけ書いて次へ進む。
- `#4`（実機調査）と、各 Issue の「実機で確かめる」条件: いま動いている PC が Windows なら、自分で確かめて結果を報告書に書く。Windows でなければ手順書（`docs/manual-checks/issue-<番号>.md`）だけを書き、その条件は未完了にする。
- `#22`（実機での通し確認）は別の PC とコンサルタントの作業を含むので、あなたは手順書だけを書き、報告書の状態は「一部未完了」にする。

### Issue 1件ごと

1. **この `GEMINI.md` を読み直す。**（長い作業の途中で決まりごとを忘れないため）
2. Issue の本文と、親の仕様書 `#3` を読む（`docs/issues/` の写し）。
3. 次を読む: `CONTEXT.md`（用語集）、`docs/adr/` 全件、`docs/product-overview.md`、`docs/mvp-build-items.md`、それまでの `docs/gemini-reports/`。DeskMate を流用する Issue では `docs/research/deskmate-survey.md` も読む。
4. 受け入れ条件ごとにテストを先に書き、失敗することを確かめてから実装する。
5. 「作業の終わり方」（5章）を行ってから、次の Issue へ進む。

## 2. 絶対に触らないもの

次のファイル・場所は**読むだけ**で、変更・削除・移動しない。

- `AGENTS.md`、`GEMINI.md`、`CONTEXT.md`、`README.md`
- `docs/adr/`、`docs/product-overview.md`、`docs/mvp-build-items.md`、`docs/research/`、`docs/agents/`、`docs/issues/`
- `.claude/`、`skills-lock.json`
- 自分の Issue 以外で作られたテスト（`tests/` の既存ファイル）
- GitHub の Issue と Pull Request の本文・ラベル・状態（close しない、コメントしない）

例外は Issue の受け入れ条件が明示的に求めるものだけ（例: `#4` は ADR 0004 の表の更新を求めている）。

## 3. 技術の決まりごと（勝手に変えない）

- 言語: Python 3.12。依存と設定は `pyproject.toml` に書く。
- 置き場所: 本体は `src/flowlens/`、テストは `tests/`。
- 構成は次の2つに分ける。
  - **記録の中核**: `src/flowlens/core/`。Windows に依存しない。Linux でも import・テストできること。無害化、除外、記号化、保存、集計、書き出しはすべてここで行う。
  - **Windows の入口**: `src/flowlens/windows/`。Windows とやり取りして観測を中核へ渡すだけで、判断しない。中核から `windows` を import しない。
- 中核の外向きの顔は1つのクラス `flowlens.core.Recorder` にまとめる。テストはこの顔と、書き出した1ファイルだけを使う。
  - 観測を受け取る: `observe(observation)`
  - 設定: 除外アプリ、保存期間、一時停止と再開、Past Import の読み込み元の選択
  - 削除: `delete(範囲)`
  - 書き出し: `export(期間, パスワード, 保存先) -> Path`
  - 観測は中核が定義する dataclass で表す。時刻はテストから差し替えられるように、時計を外から渡せるようにする。
  - 名前や引数の細部は `#5` で決めてよい。決めたら報告書に書き、以降の Issue ではそれを変えない（足すのはよい）。
- 保存: SQLite（WAL）。スキーマの版を持つ。本文の列を作らない。
- 暗号化: `pyzipper` で AES-256 の ZIP を作る。独自の暗号処理を書かない。
- 題名・ファイル名の記号化: 標準ライブラリの `hmac` と `hashlib.sha256` を使う。鍵は PC 内の保存先に置き、書き出しに含めない（ADR 0003）。
- テスト: `pytest`。確認コマンドは `python -m pytest` と `python -m ruff check .`。**Windows 以外でも中核のテストがすべて通ること。** Windows 専用のテストは作らない。Windows の入口は、利用者が実機で確かめる手順書（`docs/manual-checks/issue-<番号>.md`）を書く。
- 追加してよい依存: `pyzipper`、`pytest`、`ruff`。Windows の入口に限り、`pywin32`、`uiautomation`、`psutil` も使える。**これ以外の依存は足さない。** 必要なら標準ライブラリで書くか、その条件を未完了にして「質問」に書く。
- 通信する依存は禁止: `requests`、`httpx`、`urllib3`、`aiohttp`、`fastapi`、`flask`、`uvicorn`、`websockets`、`openai`、`anthropic`、`google-genai`、`google-generativeai`、`ollama` など。標準ライブラリの `socket`・`urllib.request`・`http.client` も使わない。
- DeskMate（https://github.com/zhaohb/deskmate 、MIT）のコードを流用したファイルは、先頭に元のファイル名と MIT の著作権表示を残す。

## 4. プライバシーの禁止事項（ADR 0001・0002 より。どの Issue でも破らない）

次のものを、保存・ログ出力・書き出しのどれにも含めない。**「取れるから取っておく」は禁止。**

- 入力した文字、文章、IME の確定内容。Enter を押した時に入力欄の値を読む処理も作らない。
- UI 部品の Name・Value・表示テキスト、TextPattern で読める本文。
- Clipboard の中身。
- パスワード欄での入力。回数も残さず、「パスワード欄の時間があった」ことだけを残す。
- ウィンドウタイトル・ファイル名・ファイルパスの生の文字列。記号と拡張子だけを残す。
- URL のパス・クエリ・フラグメント・トークン。ドメインだけを残す。
- 画面の撮影、OCR。これらを行う処理そのものを作らない。
- PC 名、ユーザー名。機器 ID はランダムな UUID にする。
- AI・LLM の呼び出し、外部への通信、利用状況の送信、更新確認。

障害調査用のログには「起動した」「データベースを開いた」程度だけを書く。業務の中身は書かない。

## 5. 作業の終わり方（Issue 1件ごと）

1. `python -m pytest` と `python -m ruff check .` を実行する。
2. 報告書 `docs/gemini-reports/issue-<番号>.md` を下の型で書く。
3. その Issue の分を、枝 `gemini/mvp` に1つ以上のコミットにまとめる。コミットの説明は英語で1行、先頭に `#<番号>` を付ける（例: `#5 Add Recorder with encrypted export`）。
4. 送る（`git push -u origin gemini/mvp`）。送れなければ報告書にそう書き、手元にコミットしたまま次へ進む。
5. マージしない。Issue を close しない。Issue や Pull Request にコメントしない。
6. 次の Issue へ進む。

### すべて終わったら

1. `docs/gemini-reports/summary.md` に、Issue ごとの状態（完了／一部未完了／着手できず）の一覧と、「質問」の一覧をまとめる。
2. `gh` が使えるなら、`gemini/mvp` から `main` 宛ての**下書き**の Pull Request を1つ作る。題名は `[Gemini] FlowLens Collector MVP`、本文は `summary.md` と同じ内容にする。`gh` が使えなければ作らない。
3. 利用者に「完了しました。まとめは docs/gemini-reports/summary.md」とだけ伝えて止まる。

### 報告書の型

```markdown
# Issue #<番号> 報告書

## 状態
完了 / 一部未完了 / 着手できず（どれか1つ）

## 受け入れ条件
- [x] 条件1 — 確かめたテスト名: `test_xxx`
- [ ] 条件2 — 未完了。理由: ...

## 触ったファイル
- `path/to/file.py`: 何をしたか1行

## 決めたこと
仕様・ADR に書いていなかったので自分で決めたこと。無ければ「なし」。

## 質問
レビュー担当に判断してほしいこと。無ければ「なし」。

## 実行したコマンドと結果
（`python -m pytest` と `python -m ruff check .` の出力の末尾をそのまま貼る）

## 実機での確認
Windows 実機で確かめる必要があること。手順書の場所。自分では確かめていないことを明記する。
```
