"""Diagnostic Export: one AES-256 encrypted ZIP holding only sanitized data.

Everything is sanitized a second time here (ADR 0002 「書き出し時にもう一度無害化する」):
exclusions are re-applied with the current settings, and every stored value is checked
again against the same rules used at recording time.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pyzipper

from flowlens.core import sanitize
from flowlens.core.storage import INTERVAL_TABLES, SCHEMA_VERSION, TABLES, Storage, ts
from flowlens.core.summary import generate_summary

APPLICATION_VERSION = "0.2.0"

_SYMBOL_RE = re.compile(r"^[0-9a-f]{16}$")

README_TEXT = """FlowLens Diagnostic Export
==========================

This archive was written by FlowLens Collector on the employee's PC.
It contains no typed text, no clipboard contents, no screenshots, no passwords
and no full URLs. Window titles and file names are keyed symbols (16 hex chars)
that cannot be reversed without a key that never left the PC.

Files
- data.sqlite            All records for the chosen period (SQLite).
- manifest.json          Period, device id (random), record counts, versions.
- summary.json           Pre-computed totals (no AI involved).
- redaction_report.json  How many records were removed or cleared on export.
- README.txt             This file.

Open with 7-Zip (Windows' built-in ZIP cannot open AES-256) and the password
the employee chose.

Two kinds of records (column is_past)
- is_past = 0  Live Capture: recorded after consent. App sessions (idle, lock and
               sleep removed), typing counts, operation keys, clipboard transfers
               (app to app, size only), clicked/focused UI element types.
- is_past = 1  Past Import: coarse footprints Windows had already kept for the
               30 days before consent (power events, app usage counters, opened
               files, visited domains). Never add these to live durations.

Main tables
- app_sessions(app_name, title_symbol, title_ext, start_time, end_time, duration_seconds)
- typing_activities(app_name, title_symbol, start_time, end_time, keystroke_count, is_password)
- operation_events(app_name, operation_type, timestamp)
- clipboard_transfers(action, source_app, target_app, data_type, data_length, copy_time, paste_time)
- control_events(app_name, event_type, control_type, automation_id, class_name, browser_domain)
- excluded_intervals(start_time, end_time, reason)  reason: pause / excluded_app
- system_events, file_events, browser_events, past_app_stats, past_import_runs (Past Import)

All times are UTC (ISO 8601). Title symbols appear in app_sessions, typing_activities
and control_events; the same symbol means the same window title.
"""


@dataclass
class _Report:
    excluded_by_table: dict[str, int]
    cleared_values: int = 0

    def as_dict(self, password_rows: int) -> dict[str, Any]:
        return {
            "excluded_app_records": sum(self.excluded_by_table.values()),
            "excluded_app_records_by_table": self.excluded_by_table,
            "password_field_typing_records": password_rows,
            "values_cleared_on_export": self.cleared_values,
            "typed_text_exported": 0,
            "clipboard_contents_exported": 0,
            "full_urls_exported": 0,
            "screenshots_exported": 0,
        }


def write_export(
    storage: Storage,
    *,
    start: datetime,
    end: datetime,
    excluded_apps: set[str],
    password: str,
    destination: Path,
    device_id: str,
    created_at: datetime,
    work_dir: Path,
) -> int:
    """Writes the encrypted export and returns the number of exported records."""
    if not password:
        raise ValueError("A password is required to encrypt the export.")
    if end < start:
        raise ValueError("The export period ends before it starts.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    # The plain SQLite copy lives next to the live database (same protection),
    # not in the system temp folder, and is removed as soon as the ZIP is written.
    with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
        db_path = Path(tmp) / "data.sqlite"
        target = Storage(db_path)
        report = _Report(excluded_by_table={})
        counts: dict[str, int] = {}
        conn = target.connect()
        try:
            for table, spec in TABLES.items():
                source_rows = (
                    storage.rows(table)
                    if table == "past_import_runs"
                    else storage.rows(table, start, end)
                )
                exported = 0
                for row in source_rows:
                    if any(
                        (row.get(col) or "").lower() in excluded_apps for col in spec.app_columns
                    ):
                        report.excluded_by_table[table] = report.excluded_by_table.get(table, 0) + 1
                        if table == "app_sessions":
                            row = {
                                "start_time": row["start_time"],
                                "end_time": row["end_time"],
                                "reason": "excluded_app",
                            }
                            if _trim(row, start, end):
                                _insert(conn, "excluded_intervals", row)
                        continue
                    if table in INTERVAL_TABLES and not _trim(row, start, end):
                        continue
                    report.cleared_values += _resanitize(row)
                    _insert(conn, table, row)
                    exported += 1
                counts[table] = exported
            conn.commit()
            counts["excluded_intervals"] = conn.execute(
                "SELECT COUNT(*) FROM excluded_intervals"
            ).fetchone()[0]
            password_rows = conn.execute(
                "SELECT COUNT(*) FROM typing_activities WHERE is_password = 1"
            ).fetchone()[0]
        finally:
            conn.close()

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "application_version": APPLICATION_VERSION,
            "export_created_at": ts(created_at),
            "period_start": ts(start),
            "period_end": ts(end),
            "device_id": device_id,
            "record_counts": counts,
            "includes_past_import": counts.get("past_import_runs", 0) > 0,
            "screenshots_included": False,
        }
        summary = generate_summary(db_path)

        partial = destination.with_name(destination.name + ".partial")
        try:
            with pyzipper.AESZipFile(
                partial, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
            ) as zf:
                zf.setpassword(password.encode("utf-8"))
                zf.setencryption(pyzipper.WZ_AES, nbits=256)
                zf.write(db_path, arcname="data.sqlite")
                zf.writestr("manifest.json", _json(manifest))
                zf.writestr("summary.json", _json(summary))
                zf.writestr("redaction_report.json", _json(report.as_dict(password_rows)))
                zf.writestr("README.txt", README_TEXT)
            os.replace(partial, destination)
        finally:
            if partial.exists():
                partial.unlink()
    return sum(counts.values())


def _trim(row: dict[str, Any], start: datetime, end: datetime) -> bool:
    """Cuts an interval to the export period. False if nothing is left."""
    row_start = max(row["start_time"], ts(start))
    row_end = min(row["end_time"], ts(end))
    duration = (datetime.fromisoformat(row_end) - datetime.fromisoformat(row_start)).total_seconds()
    if duration <= 0:
        return False
    row["start_time"], row["end_time"], row["duration_seconds"] = row_start, row_end, duration
    return True


def _resanitize(row: dict[str, Any]) -> int:
    """Re-applies the recording rules to every column. Returns how many values were cleared."""
    cleared = 0

    def put(col: str, value: Any) -> None:
        nonlocal cleared
        if row[col] != value:
            cleared += 1
            row[col] = value

    for col in list(row):
        value = row[col]
        if col in ("app_name", "source_app", "target_app"):
            name, ok = sanitize.app_name(value)
            put(col, name if ok else "other")
        elif col in ("title_symbol", "file_symbol"):
            put(col, value if value and _SYMBOL_RE.match(value) else "")
        elif col in ("title_ext", "file_ext"):
            put(col, value if value and value[1:] in sanitize.FILE_EXTENSIONS else "")
        elif col in ("browser_domain", "domain"):
            put(col, sanitize.domain(value))
        elif col in ("automation_id", "class_name", "framework_id", "control_type"):
            put(col, sanitize.identifier(value))
        elif col == "state":
            put(col, sanitize.choice(value, sanitize.CONTROL_STATES))
        elif col == "error":
            put(col, value if value and sanitize.error_code(value) == value else (value and ""))
    return cleared


def _insert(conn: Any, table: str, row: dict[str, Any]) -> None:
    cols = [c for c in TABLES[table].columns if c in row]
    marks = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({marks})",
        [row[c] for c in cols],
    )


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)
