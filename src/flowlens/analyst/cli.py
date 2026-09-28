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

from flowlens.analyst.reader import ExportError, open_export
from flowlens.analyst.summary import build_summary

SUMMARY_FILE = "analysis_summary.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flowlens.analyst",
        description="FlowLens の診断データから Analysis Summary を作ります。",
    )
    parser.add_argument("exports", nargs="+", type=Path, help="診断データ（ZIP）")
    parser.add_argument("--out", required=True, type=Path, help="結果を書き出すフォルダ")
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
                password = env_password or ask_password(f"{path.name} のパスワード: ")
                opened.append(open_export(path, password, Path(work)))
            summary = build_summary(opened, tz)
        except ExportError as exc:
            print(f"読み込めませんでした。{exc}", file=sys.stderr)
            return 1
        finally:
            for export in opened:
                export.db.close()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / SUMMARY_FILE).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"書き出しました: {args.out / SUMMARY_FILE}")
    return 0
