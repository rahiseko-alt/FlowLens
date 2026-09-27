# 引き継ぎメモ

セッションをまたいで作業を再開するための記録。**新しいものを一番上に足す。**

- 1件の区切りは行頭の `## `。書式は `docs/agents/flow-map.md` の「引き継ぎメモ」に従う。
- 保存の上限と、会話開始時に読み込む件数は `.claude/hooks/session-start.sh` が持つ。
- 追記したら `sh .claude/hooks/handover-trim.sh` を実行して件数を整える。

---

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

