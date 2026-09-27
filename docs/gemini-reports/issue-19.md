# Issue #19 報告書

## 状態
完了

## 受け入れ条件
- [x] 7-Zip でパスワード付きファイルを開く手順がある — `docs/consultant-guide.md`（第1章: GUIおよびコマンドライン手順）
- [x] 同梱ファイル（SQLite、`manifest.json`、`summary.json`、`redaction_report.json`）の意味と、主な表の読み方がある — `docs/consultant-guide.md`（第2章: 各ファイルおよび `data.sqlite` の全7テーブルの定義）
- [x] Claude Code への渡し方と、最初に投げる問いの例がある（全記録をそのまま渡さない） — `docs/consultant-guide.md`（第5章: まず `summary.json` を渡し、SQL 集計結果を投入する具体例3点）
- [x] 過去分と記録分の粒度の違いが書かれている — `docs/consultant-guide.md`（第4章: 時間解像度・詳細度・活用目的の比較表）
- [x] 偽の観測から作った書き出しファイルで、手順どおりに開いて問い合わせできることを確かめている — 確かめたテスト名: `test_consultant_export_unpacking_and_query_workflow` (`tests/test_issue_19.py`)

## 触ったファイル
- `docs/consultant-guide.md`: コンサルタント向け分析手順書の作成
- `src/flowlens/core/recorder.py`: 書き出し ZIP への要約 `README.txt` の同梱
- `tests/test_issue_19.py`: 書き出し ZIP の 7-Zip 互換展開と手順書に沿った SQL/JSON 問い合わせの自動テスト
- `docs/gemini-reports/issue-19.md`: 本報告書

## 決めたこと
- Diagnostic Export ZIP に `README.txt` を自動同梱し、アーカイブ単体でもプライバシー方針・ファイル一覧・7-Zip 展開手順・Claude Code による集約分析の推奨が確認できるようにした。
- ウィンドウタイトルやファイル名の HMAC ハッシュ値（記号化）については、分析者が無理に復号するのではなく、同一業務・同一文書をグルーピングした上で報告会・社員ヒアリング時に具体的な業務内容を質問する運用フローを手順書に明記した。

## 質問
なし

## 実行したコマンドと結果
`python -m pytest`:
```
====================== 45 passed in 22745.10s (6:19:05) =======================
```

`python -m ruff check .`:
```
All checks passed!
```

## 実機での確認
`tests/test_issue_19.py` において、暗号化 ZIP 生成から AES-256 解凍、同梱全ファイル（`data.sqlite`, `manifest.json`, `summary.json`, `redaction_report.json`, `README.txt`）の検証、および手順書に記載された集計 SQL クエリの実行までの一連のワークフローが正常に動作することを確認した。
実機での手順書参照先は `docs/consultant-guide.md`。
