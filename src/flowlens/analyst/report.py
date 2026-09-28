"""The Markdown files next to the summary: confirmation questions and instructions.

Both are built from the Analysis Summary alone, so they can only mention labels,
never symbols or device ids.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Kept as a Markdown file so it reads as a document, not code.
INSTRUCTIONS = (Path(__file__).parent / "instructions_for_claude.md").read_text(encoding="utf-8")


def _question(candidate: dict[str, Any]) -> str:
    labels = "・".join(candidate["labels"])
    steps = " → ".join(candidate.get("steps", []))
    if candidate["kind"] == "定時のファイル":
        hour = candidate["timing"]["hour"]
        return (
            f"{hour}時台によく開く{labels}は、何のファイルですか。"
            "開いて何をしていますか。毎回同じ手順ですか。"
        )
    if candidate["kind"] == "よく使うサイト":
        hour = candidate["timing"]["hour"]
        return (
            f"{candidate['days']}日にわたって開いている {steps}（{hour}時台に多い）では、"
            "何をしていますか。毎回同じ入力や確認をしていますか。"
        )
    if candidate["kind"] == "転記":
        target = f"（{labels}）" if labels else ""
        return (
            f"{steps}{target}へのコピーと貼り付けは、何を何に写していますか。"
            "1回にどれくらいの量を写しますか。"
        )
    return f"{steps} の順に使う作業は、何の作業ですか。どんなときに、何のために行いますか。"


def confirmation_questions(summary: dict[str, Any]) -> str:
    lines = [
        "# 確認したいこと（報告会用の下書き）",
        "",
        "画面やファイルの名前は、記録の段階で読めない記号にしているため、",
        "「ファイル A」のような呼び名で書いています。報告会で社員の方に伺ってください。",
        "",
    ]
    if not summary["candidates"]:
        lines.append(
            "繰り返しの候補はまだ見つかっていません。記録の日数が増えてから、もう一度分析してください。"
        )
    for number, candidate in enumerate(summary["candidates"], start=1):
        lines += [
            f"## 候補 {number}（{candidate['kind']}、"
            f"{candidate['count']}回・{candidate['days']}日）",
            "",
            f"- {_question(candidate)}",
            "- 例外や、判断が必要になる場面はありますか。",
            "",
        ]
    return "\n".join(lines) + "\n"
