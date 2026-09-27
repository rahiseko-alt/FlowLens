import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

INIT_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    window_title_hash TEXT NOT NULL,
    window_title_ext TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    is_past INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'live'
);

CREATE INDEX IF NOT EXISTS idx_app_sessions_time ON app_sessions(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_app_sessions_app ON app_sessions(app_name);
"""


class Storage:
    """Manages SQLite database for FlowLens Collector."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(INIT_SQL)
            cur = conn.execute(
                "SELECT version FROM schema_version WHERE version = ?",
                (SCHEMA_VERSION,),
            )
            if not cur.fetchone():
                conn.execute(
                    "INSERT INTO schema_version (version, updated_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now().isoformat()),
                )
            conn.commit()
        finally:
            conn.close()

    def insert_app_session(
        self,
        app_name: str,
        window_title_hash: str,
        window_title_ext: str,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        is_past: int = 0,
        source: str = "live",
    ) -> None:
        if duration_seconds <= 0:
            return
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO app_sessions (
                    app_name, window_title_hash, window_title_ext,
                    start_time, end_time, duration_seconds, is_past, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    app_name,
                    window_title_hash,
                    window_title_ext,
                    start_time.isoformat(),
                    end_time.isoformat(),
                    duration_seconds,
                    is_past,
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_app_sessions(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM app_sessions WHERE 1=1"
        params: list[Any] = []
        if start is not None:
            query += " AND end_time >= ?"
            params.append(start.isoformat())
        if end is not None:
            query += " AND start_time <= ?"
            params.append(end.isoformat())
        query += " ORDER BY start_time ASC"

        conn = self._connect()
        try:
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def count_sessions(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> int:
        query = "SELECT COUNT(*) FROM app_sessions WHERE 1=1"
        params: list[Any] = []
        if start is not None:
            query += " AND end_time >= ?"
            params.append(start.isoformat())
        if end is not None:
            query += " AND start_time <= ?"
            params.append(end.isoformat())

        conn = self._connect()
        try:
            cur = conn.execute(query, params)
            return cur.fetchone()[0]
        finally:
            conn.close()

    def export_subset(
        self, target_db_path: str | Path, start: datetime, end: datetime
    ) -> None:
        """Exports a subset of SQLite database into target_db_path for the given time range."""
        target_path = Path(target_db_path)
        if target_path.exists():
            target_path.unlink()
        target_storage = Storage(target_path)

        sessions = self.get_app_sessions(start=start, end=end)
        conn = target_storage._connect()
        try:
            for s in sessions:
                conn.execute(
                    """
                    INSERT INTO app_sessions (
                        app_name, window_title_hash, window_title_ext,
                        start_time, end_time, duration_seconds, is_past, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        s["app_name"],
                        s["window_title_hash"],
                        s["window_title_ext"],
                        s["start_time"],
                        s["end_time"],
                        s["duration_seconds"],
                        s["is_past"],
                        s["source"],
                    ),
                )
            conn.commit()
        finally:
            conn.close()
