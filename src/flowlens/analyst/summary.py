"""Counts the exports into an Analysis Summary: totals only, never rows (ADR 0006).

Live Capture (is_past = 0) and Past Import (is_past = 1) are kept in separate
sections. Times are counted in the customer's local time zone. Title and file
symbols only appear as labels (see labels.py).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime, timedelta, tzinfo
from typing import Any

from flowlens.analyst.candidates import Criteria, flows, rank, scheduled_files, transfers
from flowlens.analyst.common import local as _local
from flowlens.analyst.common import rows as _rows
from flowlens.analyst.labels import Labeler
from flowlens.analyst.reader import OpenedExport

ANALYSIS_VERSION = 1
FEW_LIVE_DAYS = 3  # below this, the summary warns that candidates are weak
WEEKDAYS = "月火水木金土日"
PERMISSION_CODES = ("1314", "PermissionError", "13", " 5")


def _share(part: float, total: float) -> float:
    return round(part / total, 3) if total else 0.0


def _split_by_hour(start: datetime, end: datetime) -> Iterator[tuple[datetime, float]]:
    """(hour start, seconds) for each local clock hour the interval touches."""
    cursor = start
    while cursor < end:
        next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        stop = min(next_hour, end)
        yield cursor, (stop - cursor).total_seconds()
        cursor = stop


def _reason(error: str | None) -> str:
    code = error or ""
    if any(part in code for part in PERMISSION_CODES):
        return "管理者権限が必要なため読めませんでした"
    return f"読めませんでした（{code}）" if code else "読めませんでした"


def build_summary(
    exports: list[OpenedExport], tz: tzinfo, criteria: Criteria = Criteria()
) -> tuple[dict[str, Any], dict[str, str]]:
    """Returns (Analysis Summary, label -> symbol table)."""
    labels = Labeler()
    summary = {
        "analysis_version": ANALYSIS_VERSION,
        "time_zone": str(tz),
        "criteria": {"min_days": criteria.min_days, "min_count": criteria.min_count},
        "basis": _basis(exports, tz),
        "live": _live(exports, tz, labels),
        "past": _past(exports, tz, labels),
    }
    pairs, without_paste, transfer_candidates = transfers(exports, tz, labels, criteria)
    summary["live"]["transfers"] = pairs
    summary["live"]["transfers_without_paste"] = without_paste
    summary["candidates"] = rank(
        scheduled_files(exports, tz, labels, criteria)
        + flows(exports, tz, criteria)
        + transfer_candidates
    )
    return summary, labels.table()


def _basis(exports: list[OpenedExport], tz: tzinfo) -> dict[str, Any]:
    record_counts: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    for export in exports:
        record_counts.update(export.manifest.get("record_counts", {}))
        for key, value in export.redaction.items():
            if isinstance(value, int):
                removed[key] += value
    live_days = {
        _local(r["start_time"], tz).date()
        for r in _rows(exports, "SELECT start_time FROM app_sessions WHERE is_past = 0")
    }
    notes = []
    if len(live_days) < FEW_LIVE_DAYS:
        notes.append(
            f"記録分が{len(live_days)}日分しかありません。操作の流れや繰り返しの候補は、"
            "日数が増えるまで参考程度に扱ってください。"
        )
    return {
        "files": len(exports),
        "people": len({e.manifest.get("device_id") for e in exports}),
        "period": {
            "start": _local(min(e.manifest["period_start"] for e in exports), tz).isoformat(),
            "end": _local(max(e.manifest["period_end"] for e in exports), tz).isoformat(),
        },
        "live_days": len(live_days),
        "record_counts": dict(sorted(record_counts.items())),
        "removed_on_export": dict(sorted(removed.items())),
        "notes": notes,
    }


def _live(exports: list[OpenedExport], tz: tzinfo, labels: Labeler) -> dict[str, Any]:
    app_seconds: Counter[str] = Counter()
    screen_seconds: Counter[tuple[str, str, str]] = Counter()
    grid: dict[str, Counter[str]] = defaultdict(Counter)
    for r in _rows(
        exports,
        "SELECT app_name, title_symbol, title_ext, start_time, end_time, duration_seconds "
        "FROM app_sessions WHERE is_past = 0",
    ):
        app_seconds[r["app_name"]] += r["duration_seconds"]
        if r["title_symbol"]:
            screen_seconds[(r["app_name"], r["title_symbol"], r["title_ext"])] += r[
                "duration_seconds"
            ]
        start, end = _local(r["start_time"], tz), _local(r["end_time"], tz)
        for hour, seconds in _split_by_hour(start, end):
            grid[WEEKDAYS[hour.weekday()]][str(hour.hour)] += seconds

    typing: dict[str, Counter[str]] = defaultdict(Counter)
    for r in _rows(
        exports,
        "SELECT app_name, keystroke_count, duration_seconds FROM typing_activities "
        "WHERE is_past = 0 AND is_password = 0",
    ):
        typing[r["app_name"]]["keystrokes"] += r["keystroke_count"]
        typing[r["app_name"]]["seconds"] += r["duration_seconds"]
    keys: dict[str, Counter[str]] = defaultdict(Counter)
    for r in _rows(
        exports, "SELECT app_name, operation_type FROM operation_events WHERE is_past = 0"
    ):
        keys[r["app_name"]][r["operation_type"]] += 1

    total = sum(app_seconds.values())
    return {
        "typing": [
            {"app": app, "keystrokes": t["keystrokes"], "seconds": round(t["seconds"])}
            for app, t in sorted(typing.items(), key=lambda i: -i[1]["keystrokes"])
        ],
        "operation_keys": [
            {"app": app, "keys": dict(k.most_common())}
            for app, k in sorted(keys.items(), key=lambda i: -sum(i[1].values()))
        ],
        "app_time": [
            {"app": app, "seconds": round(s), "share": _share(s, total)}
            for app, s in app_seconds.most_common()
        ],
        "screens": [
            {"label": labels.label(symbol, ext), "app": app, "ext": ext, "seconds": round(s)}
            for (app, symbol, ext), s in screen_seconds.most_common()
        ],
        "weekday_hour": {
            day: {hour: round(s) for hour, s in sorted(grid[day].items(), key=lambda i: int(i[0]))}
            for day in WEEKDAYS
            if day in grid
        },
    }


def _past(exports: list[OpenedExport], tz: tzinfo, labels: Labeler) -> dict[str, Any]:
    runs: Counter[str] = Counter()
    focus: Counter[str] = Counter()
    for r in _rows(exports, "SELECT app_name, run_count, focus_seconds FROM past_app_stats"):
        runs[r["app_name"]] += r["run_count"]
        focus[r["app_name"]] += r["focus_seconds"]
    total_runs, total_focus = sum(runs.values()), sum(focus.values())

    ext_opens: Counter[str] = Counter()
    file_opens: Counter[tuple[str, str]] = Counter()
    file_days: dict[tuple[str, str], set] = defaultdict(set)
    for r in _rows(exports, "SELECT file_symbol, file_ext, timestamp FROM file_events"):
        ext_opens[r["file_ext"]] += 1
        key = (r["file_symbol"], r["file_ext"])
        file_opens[key] += 1
        file_days[key].add(_local(r["timestamp"], tz).date())

    site_days: dict[str, set] = defaultdict(set)
    for r in _rows(exports, "SELECT domain, timestamp FROM browser_events"):
        site_days[r["domain"]].add(_local(r["timestamp"], tz).date())

    unreadable = {
        r["source"]: _reason(r["error"])
        for r in _rows(
            exports, "SELECT source, error FROM past_import_runs WHERE status = 'failed'"
        )
    }
    return {
        "app_usage": [
            {
                "app": app,
                "run_share": _share(runs[app], total_runs),
                "focus_share": _share(focus[app], total_focus),
            }
            for app in sorted(runs, key=lambda a: (-focus[a], -runs[a], a))
        ],
        "file_types": [{"ext": ext, "opens": n} for ext, n in ext_opens.most_common()],
        "files": [
            {
                "label": labels.label(symbol, ext),
                "ext": ext,
                "opens": n,
                "days": len(file_days[(symbol, ext)]),
            }
            for (symbol, ext), n in file_opens.most_common()
        ],
        "sites": [
            {"domain": domain, "days": len(days)}
            for domain, days in sorted(site_days.items(), key=lambda i: (-len(i[1]), i[0]))
        ],
        "unreadable_sources": [
            {"source": source, "reason": reason} for source, reason in sorted(unreadable.items())
        ],
    }
