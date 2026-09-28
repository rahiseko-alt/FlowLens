"""Opens Diagnostic Exports and checks they are ones this analyst can read."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pyzipper

SUPPORTED_SCHEMA_VERSIONS = {2}
REQUIRED_MEMBERS = ("data.sqlite", "manifest.json", "redaction_report.json")


class ExportError(Exception):
    """A file that cannot be analysed; the message is for the consultant."""

    def __init__(self, path: Path, reason: str):
        super().__init__(f"{path.name}: {reason}")


@dataclass
class OpenedExport:
    manifest: dict[str, Any]
    redaction: dict[str, Any]
    db: sqlite3.Connection


def open_export(path: Path, password: str, work_dir: Path) -> OpenedExport:
    """Decrypts `path` into `work_dir` (which the caller deletes afterwards)."""
    try:
        with pyzipper.AESZipFile(path) as zf:
            zf.setpassword(password.encode("utf-8"))
            names = set(zf.namelist())
            if not set(REQUIRED_MEMBERS) <= names:
                raise ExportError(path, "FlowLens の書き出しではありません")
            members = {name: zf.read(name) for name in REQUIRED_MEMBERS}
    except ExportError:
        raise
    except RuntimeError as exc:  # pyzipper: "Bad password for file"
        raise ExportError(path, "パスワードが違います") from exc
    except (pyzipper.BadZipFile, zipfile.BadZipFile, OSError, EOFError) as exc:
        raise ExportError(path, "ファイルが壊れているか、ZIP ではありません") from exc

    try:
        manifest = json.loads(members["manifest.json"])
        redaction = json.loads(members["redaction_report.json"])
    except ValueError as exc:
        raise ExportError(path, "FlowLens の書き出しではありません") from exc
    version = manifest.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ExportError(path, f"対応していない版です（schema_version={version}）")

    db_path = work_dir / f"{len(list(work_dir.iterdir()))}.sqlite"
    db_path.write_bytes(members["data.sqlite"])
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return OpenedExport(manifest, redaction, db)


# Tables whose rows are stretches of time. One person cannot be in two of them at
# once, so where two exports overlap, the later one only adds the uncovered part.
_CLIPPED = ("app_sessions", "excluded_intervals")
# Counts that cannot be split by time: an overlapping row is dropped instead.
_DROPPED_IF_OVERLAPPING = ("typing_activities",)
# Lifetime counters: the newest reading per app replaces older ones, never adds.
_LATEST_PER_APP = "past_app_stats"


def _record_tables(db: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT IN ('schema_version', 'export_history')"
        )
    ]


def _columns(db: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in db.execute(f"PRAGMA table_info({table})") if r[1] != "id"]


def _insert(db: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    cols = list(row)
    db.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        [row[c] for c in cols],
    )


def _uncovered(start: str, end: str, covered: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Parts of [start, end] not inside any covered interval (UTC strings sort as times)."""
    pieces = [(start, end)]
    for c_start, c_end in covered:
        next_pieces = []
        for p_start, p_end in pieces:
            if c_end <= p_start or c_start >= p_end:
                next_pieces.append((p_start, p_end))
                continue
            if p_start < c_start:
                next_pieces.append((p_start, c_start))
            if c_end < p_end:
                next_pieces.append((c_end, p_end))
        pieces = next_pieces
    return pieces


def _merge_into(base: sqlite3.Connection, other: sqlite3.Connection) -> None:
    for table in _record_tables(other):
        cols = _columns(other, table)
        existing = {tuple(r) for r in base.execute(f"SELECT {', '.join(cols)} FROM {table}")}
        for r in other.execute(f"SELECT {', '.join(cols)} FROM {table}"):
            row = dict(zip(cols, r))
            if tuple(r) in existing:
                continue
            if table == _LATEST_PER_APP:
                kept = base.execute(
                    f"SELECT last_used FROM {table} WHERE app_name = ?", (row["app_name"],)
                ).fetchone()
                if kept and kept[0] >= row["last_used"]:
                    continue
                base.execute(f"DELETE FROM {table} WHERE app_name = ?", (row["app_name"],))
                _insert(base, table, row)
            elif table in _CLIPPED or table in _DROPPED_IF_OVERLAPPING:
                covered = list(
                    base.execute(
                        f"SELECT start_time, end_time FROM {table} "
                        "WHERE start_time < ? AND end_time > ?",
                        (row["end_time"], row["start_time"]),
                    )
                )
                if not covered:
                    _insert(base, table, row)
                elif table in _CLIPPED:
                    for start, end in _uncovered(row["start_time"], row["end_time"], covered):
                        seconds = (
                            datetime.fromisoformat(end) - datetime.fromisoformat(start)
                        ).total_seconds()
                        _insert(
                            base,
                            table,
                            {
                                **row,
                                "start_time": start,
                                "end_time": end,
                                "duration_seconds": seconds,
                            },
                        )
            else:
                _insert(base, table, row)
    base.commit()


def merge_by_person(exports: list[OpenedExport]) -> list[OpenedExport]:
    """One entry per device: overlapping exports of one person are counted once."""
    people: dict[str, OpenedExport] = {}
    for export in exports:
        device = export.manifest.get("device_id", "")
        if device not in people:
            people[device] = export
            continue
        kept = people[device]
        _merge_into(kept.db, export.db)
        kept.manifest = {
            **kept.manifest,
            "period_start": min(kept.manifest["period_start"], export.manifest["period_start"]),
            "period_end": max(kept.manifest["period_end"], export.manifest["period_end"]),
        }
        kept.redaction = {
            key: kept.redaction.get(key, 0) + value
            for key, value in export.redaction.items()
            if isinstance(value, int)
        }
    return list(people.values())


def record_counts(exports: list[OpenedExport]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for export in exports:
        for table in _record_tables(export.db):
            n = export.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            counts[table] = counts.get(table, 0) + n
    return dict(sorted(counts.items()))
