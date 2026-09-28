# 引き継ぎメモ・保管庫

handover.md の保存上限（5 件）を超えて押し出された古いメモを、消さずにここへ移す。
会話開始時には読み込まれない。過去の経緯を掘り返すときだけ開く。新しいものを一番上に来るよう足す。

---
## 2026-09-27 インストーラーを GitHub で自動作成し、配布ページに置いた

**決めたこと**

- GitHub の Windows 環境で、試験・exe 作成・起動確認（`--self-check`）・インストーラー作成を自動で行う（`.github/workflows/build-windows.yml`）
- `v` で始まるタグを付けると、インストーラーが Releases ページに「実機確認前」として置かれる。最初は `v0.2.0`
- 署名していないので、初回は Windows が「PC が保護されました」と警告する（「詳細情報」→「実行」で入る）

**次にやること**

- 利用者が Releases から `flowlens_installer.exe` を入れ、`docs/manual-checks.md` の順に確かめる
- 見つかった問題を Issue にして直し、直したら新しいタグ（`v0.2.1` など）で配り直す
- 分析側の設計を再開する（`/grill-with-docs` の Q1〜Q7 が回答待ち）

**未解決の問題**

- 自動の起動確認は「部品が揃って記録できる」ことまで。画面・アイコン・フックが実際の操作で動くかは、実機でないと分からない

## 2026-09-27 Collector を作り直して main に取り込んだ

**決めたこと**

- 利用者の指示「ここから先は Claude で完結」により、Gemini の成果をもとに Claude Code が中核と Windows 側を作り直した。https://github.com/rahiseko-alt/FlowLens/pull/24 で main に取り込んだ。https://github.com/rahiseko-alt/FlowLens/pull/23 は閉じた
- 試験は61件合格（Linux）。Windows 側は実機では未確認
- 結果・残る課題・プライバシー上の残りのリスクは `docs/development-report.md`。実機確認の手順は `docs/manual-checks.md`
- パスワード管理アプリは初めから除外する。強制終了後は、タスク スケジューラが10分以内に起動し直す（社員が終了を選んだ場合は除く）

**次にやること**

- 利用者の Windows PC で `docs/manual-checks.md` を順に行う（配布物の作り方も同じ文書にある）
- 見つかった問題を Issue にして直す。実機確認が済んだら、#15〜#18、#20〜#22 を閉じる
- 分析側の設計を再開する（`/grill-with-docs` の Q1〜Q7 が回答待ち）

**未解決の問題**

- uiautomation の呼び出し、アドレスバーの識別、トレイメニュー、イベントログの時刻は、実機でないと正しいか分からない
- 過去分で1時間ごとのアプリ使用時間は取れない（SRUM を読まないため）

## 2026-09-27 Gemini の実装を点検。このままでは取り込めない

**決めたこと**

- Gemini の成果（https://github.com/rahiseko-alt/FlowLens/pull/23、枝 `gemini/mvp`）を点検した。結果は `docs/reviews/2026-09-27-gemini-mvp.md`
- 仕様どおりなのは #5 と #7 だけ。書き出しに生の個人情報が入る経路が3本あり、Windows 版は同意直後に止まる。https://github.com/rahiseko-alt/FlowLens/pull/23 は取り込まない

**次にやること**

- 直し方（Claude が直す／Gemini に差し戻す）を利用者に決めてもらう
- 分析側の設計（`/grill-with-docs` の Q1〜Q7）は、利用者の回答待ちのまま

**未解決の問題**

- Windows 側は実機で動いた形跡が無い。直したあとも実機での確認が要る

## 2026-09-27 実装は Gemini（Antigravity）に任せる。指示書を用意

**決めたこと**

- 実装は Antigravity 上の Gemini 3.8 Flash が行う。利用者はリポジトリの URL を渡すだけで、途中で指示しない。完成後に Claude Code がレビューして仕上げる
- Gemini 用の指示書は `GEMINI.md`。`AGENTS.md` の冒頭と `README.md` からもそこへ案内している。Issue の写しは `docs/issues/`
- Gemini は枝 `gemini/mvp` 1本で、決めた順に Issue を進め、Issue ごとの報告書を `docs/gemini-reports/` に残す。マージや Issue の close はしない

**次にやること**

- （済）https://github.com/rahiseko-alt/FlowLens/pull/1 と https://github.com/rahiseko-alt/FlowLens/pull/2 は main へ取り込み済み
- 利用者が Antigravity に URL を渡して実装させる
- 終わったら Claude Code で `gemini/mvp` を `/code-review` し、`docs/gemini-reports/summary.md` の質問に答え、仕上げる

**未解決の問題**

- Antigravity が `AGENTS.md` と `GEMINI.md` のどちらを優先するかは確証が無い（`AGENTS.md` の冒頭で `GEMINI.md` へ案内して補っている）
- Antigravity が動く PC が Windows かどうかで、実機確認をどこまで Gemini が行えるかが変わる
- 過去分の読み込み元で何が読めるかは、Windows 実機で未確認

## 2026-09-27 仕様書を19個の作業単位に割って発行

**決めたこと**

- https://github.com/rahiseko-alt/FlowLens/issues/3 の子として、https://github.com/rahiseko-alt/FlowLens/issues/4 〜 https://github.com/rahiseko-alt/FlowLens/issues/22 の19件を発行した（すべて `ready-for-agent`。前提となる作業単位は各本文の「Blocked by」）
- すぐ始められるのは2件: https://github.com/rahiseko-alt/FlowLens/issues/4（実機調査。利用者の Windows PC が要る）と https://github.com/rahiseko-alt/FlowLens/issues/5（最小の一本道）

**次にやること**

- https://github.com/rahiseko-alt/FlowLens/pull/1 → https://github.com/rahiseko-alt/FlowLens/pull/2 の順に取り込む
- `/implement` で https://github.com/rahiseko-alt/FlowLens/issues/5 から始める
- 並行して、利用者の Windows PC で https://github.com/rahiseko-alt/FlowLens/issues/4 を行う
- `README.md` の冒頭を FlowLens の説明に書き換える

**未解決の問題**

- 過去分の読み込み元で本当に何が読めるか、管理者権限が要る元を社員本人のインストールで読めるかは、Windows 実機で未確認
- 題名をハッシュにした粒度で業務を見分けられるかは、実データで確かめるまで分からない

## 2026-09-27 Collector MVP の仕様書を発行

**決めたこと**

- 仕様書を https://github.com/rahiseko-alt/FlowLens/issues/3 として発行した（`ready-for-agent`）
- 自動テストは「入口と出口の1か所」で行う。偽の操作・偽の過去記録を記録の中核に流し、書き出した1ファイルの中身だけを確かめる。Windows とやり取りする薄い部分は実機で手順書どおりに確かめる

**次にやること**

- https://github.com/rahiseko-alt/FlowLens/pull/1 → https://github.com/rahiseko-alt/FlowLens/pull/2 の順に取り込む
- `/to-tickets` で仕様書を作業単位に割る
- そのあと `/implement`。最初の作業単位で、Past Import の読み込み元が実機で読めるか（管理者権限の要否を含む）を確かめる
- `README.md` の冒頭を FlowLens の説明に書き換える

**未解決の問題**

- 過去分の読み込み元で本当に何が読めるか、管理者権限が要る元を社員本人のインストールで読めるかは、Windows 実機で未確認
- 題名をハッシュにした粒度で業務を見分けられるかは、実データで確かめるまで分からない

## 2026-09-27 過去30日分の読み込みを MVP の柱11に追加

**決めたこと**

- MVP は「過去をあさる（Past Import）」と「これから記録する（Live Capture）」の2本立て。柱11として追加した（ADR 0004）
- 過去分は読める範囲をできるだけ広く取り、読む元ごとに社員が選べる。初期状態はすべて選択
- 過去分にも最小データ原則を適用する（題名・ファイル名は記号化、閲覧履歴はドメインだけ）。過去分と記録分は区別して保存する
- 下書きの提出物: https://github.com/rahiseko-alt/FlowLens/pull/2（https://github.com/rahiseko-alt/FlowLens/pull/1 の上に積んである）

**次にやること**

- https://github.com/rahiseko-alt/FlowLens/pull/1 を先に取り込み、そのあと https://github.com/rahiseko-alt/FlowLens/pull/2 を取り込む
- `IMPLEMENTATION_PLAN.md` を作るかどうかを利用者に確認する（`/to-spec` で代えられる）
- そのあと `/to-spec` → `/to-tickets` → `/implement` と進む
- `README.md` の冒頭を FlowLens の説明に書き換える

**未解決の問題**

- 過去分の読み込み元（SRUM、イベントログ等）で本当に何が読めるかは、実際の Windows 機で未確認
- 管理者権限が要る元を読むには、インストーラーが管理者権限で動く必要がある。社員本人がインストールする前提と両立するか未確認
- 題名をハッシュにした粒度で業務を見分けられるかは、実データで確かめるまで分からない
- UI 部品の Name から、固定のラベルとユーザーが書いた内容を見分けられるかは未調査

## 2026-09-27 MVP の柱10本から作る項目を割り出した

**決めたこと**

- 柱ごとに作る項目を `docs/mvp-build-items.md` にまとめた
- 記録データの削除画面と保存期間（初期値30日で自動削除）は MVP に含める
- MVP の Analyst 側は手順書だけ。繰り返しを見つけるプログラムは実データを得てから作る
- ウィンドウタイトルは PC 内の鍵を使ったハッシュと拡張子だけを残す（ADR 0003）
- 下書きの提出物: この作業は https://github.com/rahiseko-alt/FlowLens/pull/1 の上に積んだ別の提出物にある

**次にやること**

- https://github.com/rahiseko-alt/FlowLens/pull/1 を先に取り込み、そのあと今回の提出物を取り込む
- `IMPLEMENTATION_PLAN.md` を作るかどうかを利用者に確認する（`/to-spec` で代えられる）
- そのあと `/to-spec` → `/to-tickets` → `/implement` と進む
- `README.md` の冒頭を FlowLens の説明に書き換える

**未解決の問題**

- UI 部品の Name から、固定のラベルとユーザーが書いた内容を見分けられるかは未調査
- 題名をハッシュにした粒度で業務を見分けられるかは、実データで確かめるまで分からない
- 実際の Windows 機では何も確かめていない

## 2026-09-27 FlowLens の設計原則と DeskMate 流用調査

**決めたこと**

- 作るものは FlowLens（PC 業務観測・業務改善診断システム）。用語は `CONTEXT.md` に定義した
- クライアント PC では AI を一切動かさない（ADR 0001）。最小データ原則: 業務フローの発見に要らないデータは保存しない（ADR 0002）
- DeskMate 流用調査の結果と5分類は `docs/research/deskmate-survey.md` にある。記録の本体（daemon）とデータベースは書き直し、監視の部品を選んで流用する方針
- 目的・一言説明・利用の流れを `docs/product-overview.md` に確定した。インストールは社員本人、渡し方は製品で決めない（手元に1ファイル保存まで）、コンサルタントは基本本人だが他者もありうる
- 価値、実装してはいけない機能、MVP のゴール（一言）と柱10本を `docs/product-overview.md` に確定した。暗号化（AES-256）は MVP に含める。コンサルタントの PC には 7-Zip が必要
- 利用者の元の仕様書の写しを `docs/research/original-spec.md` に保存した（後の合意は product-overview と ADR が優先）
- 下書きの提出物: https://github.com/rahiseko-alt/FlowLens/pull/1

**次にやること**

- MVP の柱10本から、作る項目を割り出す（利用者と合意済みの次の作業）
- 利用者の元の仕様書にある `IMPLEMENTATION_PLAN.md` を、調査結果と ADR をもとに作る（利用者の指示を待ってから）
- そのあと `/to-spec` → `/to-tickets` → `/implement` と進む
- `README.md` の冒頭を FlowLens の説明に書き換える

**未解決の問題**

- UI 部品の Name から、固定のラベルとユーザーが書いた内容を見分けられるかは未調査
- ウィンドウタイトルやファイルパスをどの粒度で残すかは未定（実データでの検証が必要）
- 実際の Windows 機では何も確かめていない

## 2026-09-21 サブエージェントの洗い直しで3件追加修正

**決めたこと**

- ここまでの2件の修正は自分だけで探していたので、サブエージェントに独立して全体を洗い直させた。
  見つかった3件を修正した
- (1) `/setup-matt-pocock-skills`を再実行すると、ベンダーのひな形で`docs/agents/domain.md`等を
  無条件に上書きし、今回までの穴埋めごと消える設計だった。`flow-map.md`のルールを
  「domain.mdが消えても1行で足りる」自己完結な内容に書き直し、加えて再実行時は
  現在の中身を読んで独自追記を残すよう`flow-map.md`にルール7を追加した
- (2) `handover-trim.sh`は上限を超えた古いメモを完全に削除する設計で、行き場が無かった。
  `docs/agents/handover-archive.md`へ退避してから削るよう書き直した（動作確認済み。
  会話開始時には読み込まれない保管庫）
- (3) `next-step`のドメイン文書チェックが、多コンテキスト構成の`CONTEXT-MAP.md`・
  `src/<context>/docs/adr/`を見ていなかったので追記した

**次にやること**

- `/grill-with-docs` で「何を作るか」を決める（前回から持ち越し。まだ未着手）
- 決まったら `/to-spec` → `/to-tickets` → `/implement` と進む
- `README.md` の冒頭をこのプロジェクトの説明に書き換える
- `docs/adr/`ができたら、`/code-review`実行時に実際にStandards軸へ渡るか、
  `/setup-matt-pocock-skills`を再実行しても穴埋めが残るか、両方まだ未検証

**未解決の問題**

- 今回もこの3件以外に穴が無いという保証は無い。サブエージェントの調査も
  「見た範囲では」の話であり、悉皆性の証明ではない

## 2026-09-21 フローを飛ばすと用語集・ADRが読まれない穴も修正

**決めたこと**

- 前回の`/code-review`修正は個別の穴を塞いだだけで、根はもっと広かった。
  `CONTEXT.md`・`docs/adr/`を読む指示は`/to-spec`等の個別スキルにしか書かれておらず、
  利用者が「そのまま作って」とフローを飛ばすと、その指示ごと消えて何も読まれない構成だった
- `docs/agents/domain.md`に「フローを飛ばしても読む」旨を明記し、`flow-map.md`（毎回自動読込）の
  ルール4にも同じ義務を追記した。`next-step`スキルも、`CONTEXT.md`/`docs/adr/`の**有無**しか
  見ていなかったのを、**中身を読んで食い違いがあれば一言伝える**よう直した

**次にやること**

- `/grill-with-docs` で「何を作るか」を決める（前回から持ち越し。まだ未着手）
- 決まったら `/to-spec` → `/to-tickets` → `/implement` と進む
- `README.md` の冒頭をこのプロジェクトの説明に書き換える
- 実際に `CONTEXT.md`・`docs/adr/` ができた後、フローを飛ばして直接実装を頼んでみて、
  今回の修正どおり読まれるか確認する（まだ未検証）

**未解決の問題**

- 今回も指示書を足しただけで、実地確認はしていない。`docs/adr/`が今も0件なので、
  「食い違いを検知して伝える」動作は一度も実際には動いていない

## 2026-09-21 ADRが検査されない欠陥を修正

**決めたこと**

- `/code-review` は `docs/adr/` を一切見ておらず、Standards担当のサブエージェントは
  事前に貼り付けた文書しか見えない隔離構成だった。ADRを書いても検査経路が無く、
  意味の無い記録になっていた
- `/code-review` 本体（vendored、編集禁止）は直さず、`docs/agents/domain.md` に橋渡し手順を追記し、
  `docs/agents/flow-map.md`（毎回自動読込）にも同じ趣旨のルールを追記して塞いだ

**次にやること**

- `/grill-with-docs` で「何を作るか」を決める（前回から持ち越し。まだ未着手）
- 決まったら `/to-spec` → `/to-tickets` → `/implement` と進む
- `README.md` の冒頭をこのプロジェクトの説明に書き換える
- 実際に `docs/adr/` にADRができた後、一度 `/code-review` を回して、
  今回の修正どおりADRがStandards軸に渡っているか確認する（まだ未検証）

**未解決の問題**

- 今回の修正は指示書（domain.md / flow-map.md）を足しただけで、
  `/code-review` を実際に走らせて動作確認はしていない


## テンプレートから作成

**決めたこと**

- この置き場所はテンプレートから複製したもの。開発の段取り（案内役・開始と終了の儀式・引き継ぎメモ）
  だけが入っており、製品のコードはまだ1行も無い
- 何を作るかはまだ決まっていない

**次にやること**

- `/grill-with-docs` で「何を作るか」を決める。私が質問を重ねるので、答えるだけでよい
- 決まったら `/to-spec` → `/to-tickets` → `/implement` と進む
- `README.md` の冒頭をこのプロジェクトの説明に書き換える（この1件も、書き換えたら消してよい）

**未解決の問題**

- 特になし
