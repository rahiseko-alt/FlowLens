"""Workflow Candidates: repetitions that meet the criteria, with a marked estimate.

An estimate is "average times per observed day x median minutes per time x 20
working days". When the time per occurrence is not known (e.g. a file open from
Past Import), the estimate is left empty and candidates are ranked by count.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import tzinfo
from typing import Any

from flowlens.analyst.common import local, rows
from flowlens.analyst.labels import Labeler
from flowlens.analyst.reader import OpenedExport

WORKING_DAYS_PER_MONTH = 20
ESTIMATE_NOTE = "推定値です。観測した期間の平均から計算しており、実際の時間とは異なります。"


@dataclass(frozen=True)
class Criteria:
    """What counts as a repetition: at least `min_count` times over `min_days` days."""

    min_days: int = 2
    min_count: int = 3

    def met(self, count: int, days: int) -> bool:
        return count >= self.min_count and days >= self.min_days


def estimate(count: int, days: int, median_seconds: float | None) -> dict[str, Any]:
    if median_seconds is None:
        return {
            "minutes_per_time": None,
            "monthly_minutes_estimate": None,
            "formula": "1回あたりの時間が分からないため、月あたりの時間は推定していません",
            "estimate_note": ESTIMATE_NOTE,
        }
    per_day = count / days
    minutes = median_seconds / 60
    return {
        "minutes_per_time": round(minutes, 1),
        "monthly_minutes_estimate": round(per_day * minutes * WORKING_DAYS_PER_MONTH),
        "formula": (
            f"1日あたり {per_day:.1f} 回 × 1回 {minutes:.1f} 分（中央値）"
            f" × {WORKING_DAYS_PER_MONTH} 日"
        ),
        "estimate_note": ESTIMATE_NOTE,
    }


def rank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Largest estimate first; candidates without an estimate after, by count and days."""
    return sorted(
        candidates,
        key=lambda c: (
            c["monthly_minutes_estimate"] is None,
            -(c["monthly_minutes_estimate"] or 0),
            -c["count"],
            -c["days"],
        ),
    )


def scheduled_files(
    exports: list[OpenedExport], tz: tzinfo, labels: Labeler, criteria: Criteria
) -> list[dict[str, Any]]:
    """The same file opened on several days (Past Import), with how aligned the hour is."""
    opened: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows(exports, "SELECT file_symbol, file_ext, timestamp FROM file_events"):
        opened[(r["file_symbol"], r["file_ext"])].append(local(r["timestamp"], tz))

    found = []
    for (symbol, ext), times in opened.items():
        days = len({t.date() for t in times})
        if not criteria.met(len(times), days):
            continue
        hour, at_hour = Counter(t.hour for t in times).most_common(1)[0]
        found.append(
            {
                "kind": "定時のファイル",
                "labels": [labels.label(symbol, ext)],
                "count": len(times),
                "days": days,
                "timing": {"hour": hour, "share": round(at_hour / len(times), 3)},
                **estimate(len(times), days, None),
            }
        )
    return found
