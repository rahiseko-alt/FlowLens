# 引き継ぎメモ

セッションをまたいで作業を再開するための記録。**新しいものを一番上に足す。**

- 1件の区切りは行頭の `## `。書式は `docs/agents/flow-map.md` の「引き継ぎメモ」に従う。
- 保存の上限と、会話開始時に読み込む件数は `.claude/hooks/session-start.sh` が持つ。
- 追記したら `sh .claude/hooks/handover-trim.sh` を実行して件数を整える。

---

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

