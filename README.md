# FlowLens

普段の PC 操作から、自動化すべき繰り返しの仕事を見つけるための観測装置です。
社員の PC に入れる Collector が、過去30日分の足跡の読み込み（Past Import）と、これから先の記録（Live Capture）を行います。
中身（入力した文字・コピーした内容・画面）は残さず、暗号化した1ファイルで書き出します。

- 何を作るか: `docs/product-overview.md`、用語は `CONTEXT.md`、判断の理由は `docs/adr/`
- 仕様書と作業単位: `docs/issues/`（GitHub の Issue #3〜#22 の写し）
- **実装担当の AI（Gemini / Antigravity）は `GEMINI.md` に従ってください。**

以下は、このリポジトリの元になったテンプレートの説明です。

## 複製したら最初にすること（テンプレート）

会話を開いて、そのまま話しかけてください。何も打たなくても、AI が
「前回の続き・いまの状態・最初の一手」を報告します。

そのうえで、次の1つだけ打てば始まります。

```
/grill-with-docs
```

AI が質問を重ねて、作りたいものの曖昧な部分を潰します。答えるだけで構いません。
決まった用語は `CONTEXT.md` に、重要な判断の理由は `docs/adr/` に書き残されるので、
次の会話にも引き継がれます。

その後、この `README.md` の冒頭をプロジェクトの説明に書き換えてください。

## 覚えるのはこの3つだけ

| 打つもの | 何が起きるか |
| --- | --- |
| `s` | 前回の続き・いまの状態・最初の一手を報告します（開始時は自動でも出ます） |
| `f` | 環境を破棄しても大丈夫な状態まで片づけ、終了して良いかを報告します |
| `/next-step` | いまどこにいて、次に何を打てばいいかを1つだけ提示します |

コマンドを覚える必要はありません。「〇〇を作りたい」と伝えるだけでも、実装前に自動で案内が入ります。

## 入っているもの

- `.claude/skills/` に [mattpocock/skills](https://github.com/mattpocock/skills) を 12 個インストール
  （`npx skills add mattpocock/skills`、`skills-lock.json` でバージョン固定）
  - ユーザー起動（このうち案内で使うもの）: `grill-with-docs` / `to-spec` / `to-tickets` / `implement` / `improve-codebase-architecture` / `setup-matt-pocock-skills`
  - モデル起動: `grilling` / `domain-modeling` / `codebase-design` / `tdd` / `code-review`
- `.claude/skills/s/`, `.claude/skills/f/`, `.claude/skills/next-step/`: この置き場所独自の案内役と儀式
- `.claude/settings.json`: 会話開始時に `docs/agents/flow-map.md` を読み込む仕組み
- `docs/agents/flow-map.md`: 進め方と、説明の書き方のルール
- `docs/agents/handover.md`: 会話をまたぐ引き継ぎメモ。区切りごとに自動で追記されます
- `AGENTS.md`: 開発フローの全体像
- `docs/agents/issue-tracker.md`: 作業指示書の置き場所は GitHub Issues
- `docs/agents/domain.md`: 用語集は `CONTEXT.md`、判断の記録は `docs/adr/`

## フロー全体

- 新規開発・機能追加: `/grill-with-docs` → 必要に応じて `/to-spec` → `/to-tickets` → `/implement`
- 設計改善: `/improve-codebase-architecture` → 候補を選択 → `/grill-with-docs` または `/codebase-design` → 以下同じ

`/implement` は `/tdd` で RED → GREEN を繰り返し、最後に `/code-review` を実行します。
詳細は [AGENTS.md](./AGENTS.md) の「Development flow」を参照してください。

## スキルの更新

```bash
npx skills update
```

スキル本体は本家のまま使う方針のため、ローカルで書き換えないでください。
