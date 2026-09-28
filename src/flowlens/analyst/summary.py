"""Counts the exports into an Analysis Summary: totals only, never rows (ADR 0006).

Live Capture (is_past = 0) and Past Import (is_past = 1) are kept in separate
sections. Times are counted in the customer's local time zone.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, tzinfo
from typing import Any

from flowlens.analyst.reader import OpenedExport

ANALYSIS_VERSION = 1
FEW_LIVE_DAYS = 3  # below this, the summary warns that candidates are weak


def _local(value: str, tz: tzinfo) -> datetime:
    return datetime.fromisoformat(value).astimezone(tz)


def build_summary(exports: list[OpenedExport], tz: tzinfo) -> dict[str, Any]:
    record_counts: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    app_seconds: Counter[str] = Counter()
    live_days: set[str] = set()
    starts, ends = [], []

    for export in exports:
        record_counts.update(export.manifest.get("record_counts", {}))
        for key, value in export.redaction.items():
            if isinstance(value, int):
                removed[key] += value
        starts.append(export.manifest["period_start"])
        ends.append(export.manifest["period_end"])
        for row in export.db.execute(
            "SELECT app_name, start_time, duration_seconds FROM app_sessions WHERE is_past = 0"
        ):
            app_seconds[row["app_name"]] += row["duration_seconds"]
            live_days.add(_local(row["start_time"], tz).date().isoformat())

    total = sum(app_seconds.values())
    notes = []
    if len(live_days) < FEW_LIVE_DAYS:
        notes.append(
            f"記録分が{len(live_days)}日分しかありません。操作の流れや繰り返しの候補は、"
            "日数が増えるまで参考程度に扱ってください。"
        )

    return {
        "analysis_version": ANALYSIS_VERSION,
        "time_zone": str(tz),
        "basis": {
            "files": len(exports),
            "people": len({e.manifest.get("device_id") for e in exports}),
            "period": {
                "start": _local(min(starts), tz).isoformat(),
                "end": _local(max(ends), tz).isoformat(),
            },
            "live_days": len(live_days),
            "record_counts": dict(sorted(record_counts.items())),
            "removed_on_export": dict(sorted(removed.items())),
            "notes": notes,
        },
        "live": {
            "app_time": [
                {
                    "app": app,
                    "seconds": round(seconds),
                    "share": round(seconds / total, 3) if total else 0,
                }
                for app, seconds in app_seconds.most_common()
            ],
        },
    }
