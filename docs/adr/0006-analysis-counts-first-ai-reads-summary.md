# 分析はプログラムが先に数え、AI は要約だけを読む。個人は比べない

Analyst 側では、プログラムが Diagnostic Export から Analysis Summary を作り、AI（Claude Code）はその要約だけを読んで「何の業務か・自動化できるか」を判断し、Proposal Report を書く。元の記録は AI に渡さない。数字はプログラムが出すので、AI が数字を作り上げる危険も減る。

1社で複数の社員の Diagnostic Export を受け取ったときは、会社単位でまとめ、Workflow Candidate は「何人に見られたか」で示す。個人ごとの比較や順位は出さない（人を評価する道具にしない）。

## Consequences

- AI に送るのは Analysis Summary だけで、題名・ファイル名は記号のまま。分析時に要約が AI の提供元へ送られることを、お客様への説明と同意書に明記する。
- 過去30日分（Past Import）では「時間の使い道」と「繰り返しの目星」を出し、操作の流れは Live Capture で裏付ける。
- 題名が記号なので、Proposal Report には必ず確認リストを付ける。
- 分析側は Claude Code が作る。
