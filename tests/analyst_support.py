"""Helpers for the analyst tests: a real export from the Collector, run through the CLI."""

from __future__ import annotations

import json
from datetime import timedelta

from conftest import PASSWORD, T0

from flowlens.analyst import main
from flowlens.core import TimeRange


def make_export(recorder, tmp_path, name="export.zip", password=PASSWORD):
    recorder.flush()
    dest = tmp_path / "exports" / name
    recorder.export(TimeRange(T0 - timedelta(days=60), T0 + timedelta(days=60)), password, dest)
    return dest


def analyze(tmp_path, *exports, passwords=None, extra=()):
    out = tmp_path / "analysis"
    answers = iter(passwords or [PASSWORD] * len(exports))
    code = main(
        [*map(str, exports), "--out", str(out), *extra], ask_password=lambda _: next(answers)
    )
    return code, out


def summary(out):
    return json.loads((out / "analysis_summary.json").read_text(encoding="utf-8"))


def run(recorder, tmp_path, extra=()):
    """Exports everything recorded so far, analyses it and returns the summary."""
    code, out = analyze(tmp_path, make_export(recorder, tmp_path), extra=extra)
    assert code == 0
    return summary(out)
