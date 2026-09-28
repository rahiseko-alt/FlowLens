"""`python -m flowlens.analyst EXPORT.zip [...] --out DIR`

Passwords are asked for each file (or taken from FLOWLENS_PASSWORD), never
passed on the command line, so they stay out of the shell history.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flowlens.analyst.candidates import Criteria
from flowlens.analyst.reader import ExportError, merge_by_person, open_export
from flowlens.analyst.report import INSTRUCTIONS, confirmation_questions
from flowlens.analyst.summary import build_summary

SUMMARY_FILE = "analysis_summary.json"
QUESTIONS_FILE = "confirmation_questions.md"
INSTRUCTIONS_FILE = "instructions_for_claude.md"
# Written next to the output folder, not inside it: Claude Code is opened in the
# output folder and can read anything there (ADR 0006).
LABELS_DIR_SUFFIX = "_do_not_send_to_ai"
LABELS_FILE = "labels.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flowlens.analyst",
        description="FlowLens の診断データから Analysis Summary を作ります。",
    )
    parser.add_argument("exports", nargs="+", type=Path, help="診断データ（ZIP）")
    parser.add_argument("--out", required=True, type=Path, help="結果を書き出すフォルダ")
    parser.add_argument(
        "--min-days", type=int, default=Criteria.min_days, help="繰り返しとみなす最少の日数"
    )
    parser.add_argument(
        "--min-count", type=int, default=Criteria.min_count, help="繰り返しとみなす最少の回数"
    )
    parser.add_argument("--tz", default="Asia/Tokyo", help="集計に使う地域の時刻（既定: 日本時間）")
    return parser


def main(
    argv: list[str] | None = None,
    ask_password: Callable[[str], str] = getpass.getpass,
) -> int:
    args = _parser().parse_args(argv)
    try:
        tz = ZoneInfo(args.tz)
    except (ZoneInfoNotFoundError, ValueError):
        print(f"地域の時刻が分かりません: {args.tz}", file=sys.stderr)
        return 2

    env_password = os.environ.get("FLOWLENS_PASSWORD")
    with tempfile.TemporaryDirectory(prefix="flowlens-analyst-") as work:
        opened = []
        try:
            for path in args.exports:
                if not path.is_file():
                    raise ExportError(path, "ファイルが見つかりません")
                password = env_password or ask_password(f"{path.name} のパスワード: ")
                opened.append(open_export(path, password, Path(work)))
            summary, labels = build_summary(
                merge_by_person(opened),
                tz,
                Criteria(min_days=args.min_days, min_count=args.min_count),
                files=len(opened),
            )
        except ExportError as exc:
            print(f"読み込めませんでした。{exc}", file=sys.stderr)
            return 1
        finally:
            for export in opened:
                export.db.close()

    labels_dir = args.out.parent / f"{args.out.name}{LABELS_DIR_SUFFIX}"
    outputs = {
        args.out / SUMMARY_FILE: json.dumps(summary, ensure_ascii=False, indent=2),
        args.out / QUESTIONS_FILE: confirmation_questions(summary),
        args.out / INSTRUCTIONS_FILE: INSTRUCTIONS,
        labels_dir / LABELS_FILE: json.dumps(labels, ensure_ascii=False, indent=2),
    }
    for target, text in outputs.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(f"書き出しました: {args.out / SUMMARY_FILE}")
    return 0
