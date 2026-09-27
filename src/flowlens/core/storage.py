"""SQLite storage for the Collector.

Every table that holds records is described once in TABLES; insertion, deletion,
retention and export all walk that description, so a new table is added in one place.
No table has a column for user content (ADR 0002).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2


def ts(value: datetime) -> str:
    """Stores every time as a fixed-width UTC string, so text order equals time order."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class TableSpec:
    columns: tuple[str, ...]
    start: str  # column compared with the end of a range
    end: str  # column compared with the start of a range (same as start for points)
    app_columns: tuple[str, ...] = ()
    unique: tuple[str, ...] = ()


TABLES: dict[str, TableSpec] = {
    "app_sessions": TableSpec(
        (
            "app_name",
            "title_symbol",
            "title_ext",
            "start_time",
            "end_time",
            "duration_seconds",
            "is_past",
            "source",
        ),
        "start_time",
        "end_time",
        ("app_name",),
        ("app_name", "title_symbol", "start_time", "is_past", "source"),
    ),
    "typing_activities": TableSpec(
        (
            "app_name",
            "title_symbol",
            "start_time",
            "end_time",
            "duration_seconds",
            "keystroke_count",
            "is_password",
            "is_past",
            "source",
        ),
        "start_time",
        "end_time",
        ("app_name",),
    ),
    "operation_events": TableSpec(
        ("app_name", "operation_type", "timestamp", "is_past", "source"),
        "timestamp",
        "timestamp",
        ("app_name",),
    ),
    "clipboard_transfers": TableSpec(
        (
            "action",
            "source_app",
            "target_app",
            "data_type",
            "data_length",
            "copy_time",
            "paste_time",
            "is_past",
            "source",
        ),
        "copy_time",
        "copy_time",
        ("source_app", "target_app"),
    ),
    "control_events": TableSpec(
        (
            "app_name",
            "title_symbol",
            "event_type",
            "control_type",
            "automation_id",
            "class_name",
            "framework_id",
            "state",
            "browser_domain",
            "timestamp",
            "is_past",
            "source",
        ),
        "timestamp",
        "timestamp",
        ("app_name",),
    ),
    "excluded_intervals": TableSpec(
        ("start_time", "end_time", "duration_seconds", "reason"),
        "start_time",
        "end_time",
    ),
    "system_events": TableSpec(
        ("event_type", "timestamp", "is_past", "source"),
        "timestamp",
        "timestamp",
        (),
        ("event_type", "timestamp", "source"),
    ),
    "file_events": TableSpec(
        ("app_name", "file_symbol", "file_ext", "timestamp", "is_past", "source"),
        "timestamp",
        "timestamp",
        ("app_name",),
        ("file_symbol", "timestamp", "source"),
    ),
    "browser_events": TableSpec(
        ("app_name", "domain", "timestamp", "is_past", "source"),
        "timestamp",
        "timestamp",
        ("app_name",),
        ("app_name", "domain", "timestamp", "source"),
    ),
    "past_app_stats": TableSpec(
        ("app_name", "last_used", "run_count", "focus_seconds", "is_past", "source"),
        "last_used",
        "last_used",
        ("app_name",),
        ("app_name", "source"),
    ),
    "past_import_runs": TableSpec(
        ("source", "run_at", "status", "record_count", "error"),
        "run_at",
        "run_at",
    ),
}

INTERVAL_TABLES = ("app_sessions", "excluded_intervals")

_COLUMN_TYPES = {
    "duration_seconds": "REAL NOT NULL",
    "focus_seconds": "REAL NOT NULL DEFAULT 0",
    "is_past": "INTEGER NOT NULL DEFAULT 0",
    "is_password": "INTEGER NOT NULL DEFAULT 0",
    "keystroke_count": "INTEGER NOT NULL DEFAULT 0",
    "data_length": "INTEGER NOT NULL DEFAULT 0",
    "run_count": "INTEGER NOT NULL DEFAULT 0",
    "record_count": "INTEGER NOT NULL DEFAULT 0",
    "paste_time": "TEXT",
    "error": "TEXT",
}


def _schema_sql() -> str:
    parts = [
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);",
        "CREATE TABLE IF NOT EXISTS export_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL, "
        "record_count INTEGER NOT NULL);",
    ]
    for name, spec in TABLES.items():
        cols = ", ".join(f"{c} {_COLUMN_TYPES.get(c, 'TEXT NOT NULL')}" for c in spec.columns)
        parts.append(
            f"CREATE TABLE IF NOT EXISTS {name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols});"
        )
        parts.append(f"CREATE INDEX IF NOT EXISTS idx_{name}_time ON {name}({spec.start});")
        if spec.unique:
            parts.append(
                f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{name} ON {name}({', '.join(spec.unique)});"
            )
    return "\n".join(parts)


class Storage:
    """A thin, content-free layer over one SQLite file.

    One connection is kept open and shared by the threads that call the Recorder;
    a lock serialises access to it.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = self._open()
        self._init_db()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def connect(self) -> sqlite3.Connection:
        """A separate connection, for building an export database."""
        return self._open()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_db(self) -> None:
        with self._lock:
            conn = self._conn
            has_version = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            ).fetchone()
            if has_version:
                row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
                if row[0] is not None and row[0] < SCHEMA_VERSION:
                    # Pre-release schema: no data worth migrating. Start clean.
                    names = [
                        r[0]
                        for r in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name NOT LIKE 'sqlite_%'"
                        )
                    ]
                    for name in names:
                        conn.execute(f"DROP TABLE IF EXISTS {name}")
            conn.executescript(_schema_sql())
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
            conn.commit()

    def insert(self, table: str, row: dict[str, Any]) -> bool:
        """Inserts one row; returns False if a unique index says it is already stored."""
        return self.insert_many(table, [row]) > 0

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Inserts rows in one transaction; returns how many were new."""
        spec = TABLES[table]
        sql = (
            f"INSERT OR IGNORE INTO {table} ({', '.join(spec.columns)}) "
            f"VALUES ({', '.join('?' for _ in spec.columns)})"
        )
        return self._write(sql, spec, rows)

    def upsert_many(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Inserts rows, replacing those that share the table's unique key."""
        spec = TABLES[table]
        updates = ", ".join(f"{c} = excluded.{c}" for c in spec.columns if c not in spec.unique)
        sql = (
            f"INSERT INTO {table} ({', '.join(spec.columns)}) "
            f"VALUES ({', '.join('?' for _ in spec.columns)}) "
            f"ON CONFLICT({', '.join(spec.unique)}) DO UPDATE SET {updates}"
        )
        return self._write(sql, spec, rows)

    def _write(self, sql: str, spec: TableSpec, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with self._lock:
            before = self._conn.total_changes
            with self._conn:
                for row in rows:
                    self._conn.execute(sql, [_to_db(row.get(c)) for c in spec.columns])
            return self._conn.total_changes - before

    def rows(
        self, table: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Rows of `table` that touch [start, end]."""
        spec = TABLES[table]
        query = f"SELECT {', '.join(spec.columns)} FROM {table} WHERE 1=1"
        params: list[str] = []
        if start is not None:
            query += f" AND {spec.end} >= ?"
            params.append(ts(start))
        if end is not None:
            query += f" AND {spec.start} <= ?"
            params.append(ts(end))
        query += f" ORDER BY {spec.start}"
        with self._lock:
            return [dict(row) for row in self._conn.execute(query, params)]

    def delete_range(self, start: datetime | None, end: datetime | None) -> None:
        """Deletes every record that touches [start, end] (None = open end)."""
        deleted = 0
        with self._lock, self._conn:
            for name, spec in TABLES.items():
                query = f"DELETE FROM {name} WHERE 1=1"
                params: list[str] = []
                if start is not None:
                    query += f" AND {spec.end} >= ?"
                    params.append(ts(start))
                if end is not None:
                    query += f" AND {spec.start} <= ?"
                    params.append(ts(end))
                deleted += self._conn.execute(query, params).rowcount
        if deleted:
            self._reclaim_space()

    def delete_before(self, cutoff: datetime) -> int:
        """Retention: deletes every record that ended before `cutoff`."""
        deleted = 0
        with self._lock, self._conn:
            for name, spec in TABLES.items():
                deleted += self._conn.execute(
                    f"DELETE FROM {name} WHERE {spec.end} < ?", (ts(cutoff),)
                ).rowcount
            self._conn.execute("DELETE FROM export_history WHERE created_at < ?", (ts(cutoff),))
        if deleted:
            self._reclaim_space()
        return deleted

    def _reclaim_space(self) -> None:
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.isolation_level = None
                self._conn.execute("VACUUM")
            except sqlite3.OperationalError:
                pass  # another connection is busy; space is reclaimed next time
            finally:
                self._conn.isolation_level = ""

    def record_export(self, created_at: datetime, start: datetime, end: datetime, count: int):
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO export_history (created_at, period_start, period_end, record_count) "
                "VALUES (?, ?, ?, ?)",
                (ts(created_at), ts(start), ts(end), count),
            )

    def live_stats(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(start_time), COALESCE(SUM(duration_seconds), 0), COUNT(*) "
                "FROM app_sessions WHERE is_past = 0"
            ).fetchone()
        return {
            "first_live_session": row[0],
            "live_seconds": float(row[1]),
            "live_session_count": int(row[2]),
        }


def _to_db(value: Any) -> Any:
    if isinstance(value, datetime):
        return ts(value)
    if isinstance(value, bool):
        return int(value)
    return value
