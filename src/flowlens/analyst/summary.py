"""Counts the exports into an Analysis Summary: totals only, never rows (ADR 0006).

Live Capture (is_past = 0) and Past Import (is_past = 1) are kept in separate
sections. Times are counted in the customer's local time zone. Title and file
symbols only appear as labels (see labels.py).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

from flowlens.analyst.candidates import (
    Criteria,
    flows,
    frequent_sites,
    keep_top,
    rank,
    scheduled_files,
    transfers,
)
from flowlens.analyst.common import local as _local
from flowlens.analyst.common import rows as _rows
from flowlens.analyst.labels import Labeler
from flowlens.analyst.reader import OpenedExport, record_counts

ANALYSIS_VERSION = 1
FEW_LIVE_DAYS = 3  # below this, the summary warns that candidates are weak
WEEKDAYS = "月火水木金土日"
# Windows error codes meaning "access denied" / "a required privilege is not held".
PERMISSION_WINERRORS = {"5", "1314"}


def _share(part: float, total: float) -> float:
    return round(part / total, 3) if total else 0.0


def _split_by_hour(start: datetime, end: datetime, tz: tzinfo) -> Iterator[tuple[datetime, float]]:
    """(local time, seconds) for each local clock hour the interval touches.

    Steps in real (UTC) time, so an hour repeated or skipped by a clock change is
    counted as the time that actually passed.
    """
    cursor, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    while cursor < end:
        here = cursor.astimezone(tz)
        into_hour = timedelta(
            minutes=here.minute, seconds=here.second, microseconds=here.microsecond
        )
        stop = min(cursor + timedelta(hours=1) - into_hour, end)
        yield here, (stop - cursor).total_seconds()
        cursor = stop


def _reason(error: str | None) -> str:
    """Error codes look like "PermissionError 13" or "OSError 1314" (name, then code)."""
    name, _, code = (error or "").partition(" ")
    if name == "PermissionError" or code in PERMISSION_WINERRORS:
        return "管理者権限が必要なため読めませんでした"
    return f"読めませんでした（{error}）" if error else "読めませんでした"


def _clock(minutes: float) -> str:
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def _pc_hours(first_last: dict[tuple[str, Any], list]) -> dict[str, Any]:
    """Typical start and end of PC use per day, over all people and days (no per-person
    figures). Median, so a late night or an early start does not move it much."""
    if not first_last:
        return {"days": 0, "typical_first": None, "typical_last": None, "days_by_weekday": {}}
    firsts = sorted(f.hour * 60 + f.minute for f, _ in first_last.values())
    lasts = sorted(last.hour * 60 + last.minute for _, last in first_last.values())
    weekdays = Counter(WEEKDAYS[day.weekday()] for _, day in first_last)
    return {
        "days": len(first_last),
        "typical_first": _clock(firsts[len(firsts) // 2]),
        "typical_last": _clock(lasts[len(lasts) // 2]),
        "days_by_weekday": {d: weekdays[d] for d in WEEKDAYS if d in weekdays},
    }


def build_summary(
    exports: list[OpenedExport], tz: tzinfo, criteria: Criteria = Criteria(), files: int = 0
) -> tuple[dict[str, Any], dict[str, str]]:
    """Returns (Analysis Summary, label -> symbol table).

    `exports` holds one entry per person (see merge_by_person); `files` is how many
    files they came from.
    """
    labels = Labeler()
    summary = {
        "analysis_version": ANALYSIS_VERSION,
        "time_zone": str(tz),
        "criteria": {"min_days": criteria.min_days, "min_count": criteria.min_count},
        "basis": _basis(exports, tz, files or len(exports)),
        "live": _live(exports, tz, labels),
        "past": _past(exports, tz, labels),
    }
    pairs, without_paste, transfer_candidates = transfers(exports, tz, labels, criteria)
    summary["live"]["transfers"] = pairs
    summary["live"]["transfers_without_paste"] = without_paste
    summary["candidates"], summary["candidates_left_out"] = keep_top(
        rank(
            scheduled_files(exports, tz, labels, criteria)
            + frequent_sites(exports, tz, criteria)
            + flows(exports, tz, criteria)
            + transfer_candidates
        )
    )
    return summary, labels.table()


def _basis(exports: list[OpenedExport], tz: tzinfo, files: int) -> dict[str, Any]:
    removed: Counter[str] = Counter()
    for export in exports:
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
        "files": files,
        "people": len({e.manifest.get("device_id") for e in exports}),
        "period": {
            "start": _local(min(e.manifest["period_start"] for e in exports), tz).isoformat(),
            "end": _local(max(e.manifest["period_end"] for e in exports), tz).isoformat(),
        },
        "live_days": len(live_days),
        "record_counts": record_counts(exports),
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
        start = datetime.fromisoformat(r["start_time"])
        end = datetime.fromisoformat(r["end_time"])
        for hour, seconds in _split_by_hour(start, end, tz):
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
        if not r["file_symbol"]:
            continue  # name cleared on export: counts for the type, not as a file
        key = (r["file_symbol"], r["file_ext"])
        file_opens[key] += 1
        file_days[key].add(_local(r["timestamp"], tz).date())

    site_days: dict[str, set] = defaultdict(set)
    for r in _rows(exports, "SELECT domain, timestamp FROM browser_events"):
        site_days[r["domain"]].add(_local(r["timestamp"], tz).date())

    # First and last PC event per day (boot, resume, sleep, shutdown...): the working hours.
    first_last: dict[tuple[str, Any], list] = {}
    for export in exports:
        person = export.manifest.get("device_id", "")
        for r in export.db.execute("SELECT timestamp FROM system_events"):
            t = _local(r["timestamp"], tz)
            key = (person, t.date())
            span = first_last.setdefault(key, [t, t])
            span[0], span[1] = min(span[0], t), max(span[1], t)

    latest: dict[str, Any] = {}
    for r in _rows(exports, "SELECT source, status, error FROM past_import_runs ORDER BY run_at"):
        latest[r["source"]] = r  # a later run (e.g. read again) replaces an earlier one
    unreadable = {
        source: _reason(r["error"]) for source, r in latest.items() if r["status"] == "failed"
    }
    return {
        "pc_hours": _pc_hours(first_last),
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
