# 引き継ぎメモ

セッションをまたいで作業を再開するための記録。**新しいものを一番上に足す。**

- 1件の区切りは行頭の `## `。書式は `docs/agents/flow-map.md` の「引き継ぎメモ」に従う。
- 保存の上限と、会話開始時に読み込む件数は `.claude/hooks/session-start.sh` が持つ。
- 追記したら `sh .claude/hooks/handover-trim.sh` を実行して件数を整える。

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

