"""Workflow Candidates: repetitions that meet the criteria, with a marked estimate.

An estimate is "average times per observed day x median minutes per time x 20
working days". When the time per occurrence is not known (e.g. a file open from
Past Import), the estimate is left empty and candidates are ranked by count.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any

from flowlens.analyst.common import local
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
    people: dict[tuple[str, str], set] = defaultdict(set)
    for export in exports:
        for r in export.db.execute("SELECT file_symbol, file_ext, timestamp FROM file_events"):
            opened[(r["file_symbol"], r["file_ext"])].append(local(r["timestamp"], tz))
            people[(r["file_symbol"], r["file_ext"])].add(export.manifest.get("device_id", ""))

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
                "people": len(people[(symbol, ext)]),
                "timing": {"hour": hour, "share": round(at_hour / len(times), 3)},
                **estimate(len(times), days, None),
            }
        )
    return found


GLIMPSE_SECONDS = 5  # a window shown for less than this is passing through, not work
BREAK_SECONDS = 120  # a longer gap (away, locked, paused) ends a flow
FLOW_LENGTHS = (2, 3, 4)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _segments(export: OpenedExport) -> list[list[dict[str, Any]]]:
    """Runs of Live Capture work without a break; glimpses dropped, repeats merged."""
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for r in export.db.execute(
        "SELECT app_name, start_time, end_time, duration_seconds FROM app_sessions "
        "WHERE is_past = 0 ORDER BY start_time"
    ):
        if r["duration_seconds"] < GLIMPSE_SECONDS:
            continue
        start, end = datetime.fromisoformat(r["start_time"]), datetime.fromisoformat(r["end_time"])
        if current and (start - current[-1]["end"]).total_seconds() > BREAK_SECONDS:
            segments.append(current)
            current = []
        if current and current[-1]["app"] == r["app_name"]:
            current[-1]["end"] = end
        else:
            current.append({"app": r["app_name"], "start": start, "end": end})
    if current:
        segments.append(current)
    return segments


def flows(exports: list[OpenedExport], tz: tzinfo, criteria: Criteria) -> list[dict[str, Any]]:
    """Repeated sequences of 2-4 apps. A shorter sequence that only ever happens inside
    a longer candidate is left out; one that also happens on its own is kept and names
    the longer ones it is part of, so the two are not added up."""
    seen: dict[tuple[str, ...], list[tuple[Any, float, str]]] = defaultdict(list)
    for export in exports:
        person = export.manifest.get("device_id", "")
        for segment in _segments(export):
            for n in FLOW_LENGTHS:
                for i in range(len(segment) - n + 1):
                    window = segment[i : i + n]
                    steps = tuple(step["app"] for step in window)
                    seconds = (window[-1]["end"] - window[0]["start"]).total_seconds()
                    seen[steps].append((window[0]["start"].astimezone(tz).date(), seconds, person))

    found = {}
    for steps, hits in seen.items():
        days = len({day for day, _, _ in hits})
        if criteria.met(len(hits), days):
            found[steps] = (hits, days)

    def inside(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
        return len(short) < len(long) and any(
            long[i : i + len(short)] == short for i in range(len(long) - len(short) + 1)
        )

    result = []
    for steps, (hits, days) in found.items():
        longer = [other for other in found if inside(steps, other)]
        if any(len(found[other][0]) == len(hits) for other in longer):
            continue  # never happens apart from the longer flow
        candidate = {
            "kind": "流れ",
            "steps": list(steps),
            "labels": [],
            "count": len(hits),
            "days": days,
            "people": len({person for _, _, person in hits}),
            **estimate(len(hits), days, _median([s for _, s, _ in hits])),
        }
        if longer:
            candidate["contained_in"] = [list(other) for other in sorted(longer)]
        result.append(candidate)
    return result


def _screen_at(sessions: list[dict[str, Any]], moment: datetime) -> dict[str, Any] | None:
    starts = [s["start"] for s in sessions]
    i = bisect_right(starts, moment) - 1
    if i >= 0 and sessions[i]["start"] <= moment <= sessions[i]["end"]:
        return sessions[i]
    return None


def transfers(
    exports: list[OpenedExport], tz: tzinfo, labels: Labeler, criteria: Criteria
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    """(pairs, transfers without a paste, candidates) for copy -> paste in Live Capture."""
    pairs: Counter[tuple[str, str]] = Counter()
    without_paste = 0
    grouped: dict[tuple[str, str, str, str], list[tuple[Any, float, str]]] = defaultdict(list)
    for export in exports:
        person = export.manifest.get("device_id", "")
        sessions = [
            {
                "start": datetime.fromisoformat(r["start_time"]),
                "end": datetime.fromisoformat(r["end_time"]),
                "symbol": r["title_symbol"],
                "ext": r["title_ext"],
            }
            for r in export.db.execute(
                "SELECT start_time, end_time, title_symbol, title_ext FROM app_sessions "
                "WHERE is_past = 0 ORDER BY start_time"
            )
        ]
        for r in export.db.execute(
            "SELECT source_app, target_app, copy_time, paste_time FROM clipboard_transfers "
            "WHERE is_past = 0"
        ):
            if not r["target_app"] or not r["paste_time"]:
                without_paste += 1
                continue
            pairs[(r["source_app"], r["target_app"])] += 1
            copied, pasted = (datetime.fromisoformat(r[c]) for c in ("copy_time", "paste_time"))
            screen = _screen_at(sessions, pasted) or {"symbol": "", "ext": ""}
            key = (r["source_app"], r["target_app"], screen["symbol"], screen["ext"])
            seconds = max((pasted - copied).total_seconds(), 0.0)
            grouped[key].append((copied.astimezone(tz).date(), seconds, person))

    found = []
    for (source, target, symbol, ext), hits in grouped.items():
        days = len({day for day, _, _ in hits})
        if not criteria.met(len(hits), days):
            continue
        found.append(
            {
                "kind": "転記",
                "steps": [source, target],
                "labels": [labels.label(symbol, ext)] if symbol else [],
                "count": len(hits),
                "days": days,
                "people": len({person for _, _, person in hits}),
                **estimate(len(hits), days, _median([s for _, s, _ in hits])),
            }
        )
    listed = [{"from": s, "to": t, "count": n} for (s, t), n in pairs.most_common()]
    return listed, without_paste, found
