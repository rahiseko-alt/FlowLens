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

CREATE TABLE IF NOT EXISTS typing_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    window_title_hash TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    keystroke_count INTEGER NOT NULL,
    is_password INTEGER NOT NULL DEFAULT 0,
    is_past INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'live'
);

CREATE TABLE IF NOT EXISTS operation_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    is_past INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'live'
);

CREATE TABLE IF NOT EXISTS clipboard_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_app TEXT NOT NULL,
    target_app TEXT NOT NULL DEFAULT '',
    data_type TEXT NOT NULL DEFAULT 'text',
    data_length INTEGER NOT NULL DEFAULT 0,
    copy_time TEXT NOT NULL,
    paste_time TEXT,
    is_past INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'live'
);

CREATE TABLE IF NOT EXISTS control_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    window_title_hash TEXT NOT NULL,
    event_type TEXT NOT NULL,
    control_type TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    class_name TEXT NOT NULL,
    framework_id TEXT NOT NULL,
    state TEXT NOT NULL,
    browser_domain TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    is_past INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'live'
);

CREATE TABLE IF NOT EXISTS excluded_intervals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    reason TEXT NOT NULL DEFAULT 'excluded_app'
);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    is_past INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL DEFAULT '',
    file_hash TEXT NOT NULL,
    file_ext TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    is_past INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS browser_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    browser_domain TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    is_past INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_sessions_unique ON app_sessions(
    app_name, window_title_hash, start_time, end_time, is_past, source
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_file_events_unique ON file_events(
    file_hash, timestamp, source
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_browser_events_unique ON browser_events(
    browser_domain, timestamp, source
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_events_unique ON system_events(
    event_type, timestamp, source
);

CREATE INDEX IF NOT EXISTS idx_app_sessions_time ON app_sessions(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_app_sessions_app ON app_sessions(app_name);
CREATE INDEX IF NOT EXISTS idx_typing_time ON typing_activities(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_operation_time ON operation_types(timestamp);
CREATE INDEX IF NOT EXISTS idx_clipboard_time ON clipboard_transfers(copy_time);
CREATE INDEX IF NOT EXISTS idx_control_time ON control_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_excluded_time ON excluded_intervals(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_file_time ON file_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_browser_time ON browser_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_system_time ON system_events(timestamp);
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
    ) -> bool:
        if duration_seconds <= 0:
            return False
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO app_sessions (
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
            return cur.rowcount > 0
        finally:
            conn.close()

    def insert_excluded_interval(
        self,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        reason: str = "excluded_app",
    ) -> None:
        if duration_seconds <= 0:
            return
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO excluded_intervals (
                    start_time, end_time, duration_seconds, reason
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    start_time.isoformat(),
                    end_time.isoformat(),
                    duration_seconds,
                    reason,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_typing_activity(
        self,
        app_name: str,
        window_title_hash: str,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        keystroke_count: int,
        is_password: int = 0,
        is_past: int = 0,
        source: str = "live",
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO typing_activities (
                    app_name, window_title_hash, start_time, end_time,
                    duration_seconds, keystroke_count, is_password, is_past, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    app_name,
                    window_title_hash,
                    start_time.isoformat(),
                    end_time.isoformat(),
                    duration_seconds,
                    keystroke_count,
                    is_password,
                    is_past,
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_operation_type(
        self,
        app_name: str,
        operation_type: str,
        timestamp: datetime,
        is_past: int = 0,
        source: str = "live",
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO operation_types (
                    app_name, operation_type, timestamp, is_past, source
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    app_name,
                    operation_type,
                    timestamp.isoformat(),
                    is_past,
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_clipboard_transfer(
        self,
        source_app: str,
        target_app: str,
        data_type: str,
        data_length: int,
        copy_time: datetime,
        paste_time: datetime | None = None,
        is_past: int = 0,
        source: str = "live",
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO clipboard_transfers (
                    source_app, target_app, data_type, data_length,
                    copy_time, paste_time, is_past, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_app,
                    target_app,
                    data_type,
                    data_length,
                    copy_time.isoformat(),
                    paste_time.isoformat() if paste_time else None,
                    is_past,
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_control_event(
        self,
        app_name: str,
        window_title_hash: str,
        event_type: str,
        control_type: str,
        automation_id: str,
        class_name: str,
        framework_id: str,
        state: str,
        browser_domain: str,
        timestamp: datetime,
        is_past: int = 0,
        source: str = "live",
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO control_events (
                    app_name, window_title_hash, event_type, control_type,
                    automation_id, class_name, framework_id, state,
                    browser_domain, timestamp, is_past, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    app_name,
                    window_title_hash,
                    event_type,
                    control_type,
                    automation_id,
                    class_name,
                    framework_id,
                    state,
                    browser_domain,
                    timestamp.isoformat(),
                    is_past,
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_system_event(
        self,
        event_type: str,
        timestamp: datetime,
        is_past: int = 1,
        source: str = "event_log",
    ) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO system_events (
                    event_type, timestamp, is_past, source
                ) VALUES (?, ?, ?, ?)
                """,
                (event_type, timestamp.isoformat(), is_past, source),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def insert_file_event(
        self,
        file_hash: str,
        file_ext: str,
        timestamp: datetime,
        app_name: str = "",
        is_past: int = 1,
        source: str = "recent_files",
    ) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO file_events (
                    app_name, file_hash, file_ext, timestamp, is_past, source
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (app_name, file_hash, file_ext, timestamp.isoformat(), is_past, source),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def insert_browser_event(
        self,
        browser_domain: str,
        timestamp: datetime,
        is_past: int = 1,
        source: str = "chrome_history",
    ) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO browser_events (
                    browser_domain, timestamp, is_past, source
                ) VALUES (?, ?, ?, ?)
                """,
                (browser_domain, timestamp.isoformat(), is_past, source),
            )
            conn.commit()
            return cur.rowcount > 0
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
        self,
        target_db_path: str | Path,
        start: datetime,
        end: datetime,
        excluded_apps: set[str] | None = None,
    ) -> dict[str, int]:
        """Exports a subset of SQLite database into target_db_path for the given time range,

        applying re-redaction against excluded_apps and returning redaction counts.
        """
        ex_apps = {a.lower().strip() for a in (excluded_apps or set())}
        target_path = Path(target_db_path)
        if target_path.exists():
            target_path.unlink()
        target_storage = Storage(target_path)

        redacted_sessions = 0
        redacted_typing = 0
        redacted_operations = 0
        redacted_clipboard = 0
        redacted_control = 0

        sessions = self.get_app_sessions(start=start, end=end)
        conn = target_storage._connect()
        try:
            for s in sessions:
                if s["app_name"].lower() in ex_apps:
                    redacted_sessions += 1
                    # Convert redacted session to excluded_intervals
                    conn.execute(
                        """
                        INSERT INTO excluded_intervals (
                            start_time, end_time, duration_seconds, reason
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (s["start_time"], s["end_time"], s["duration_seconds"], "excluded_app"),
                    )
                else:
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

            src_conn = self._connect()
            try:
                # Export typing activities
                cur = src_conn.execute(
                    "SELECT * FROM typing_activities WHERE end_time >= ? AND start_time <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for t in cur.fetchall():
                    if t["app_name"].lower() in ex_apps:
                        redacted_typing += 1
                    else:
                        conn.execute(
                            """
                            INSERT INTO typing_activities (
                                app_name, window_title_hash, start_time, end_time,
                                duration_seconds, keystroke_count, is_password, is_past, source
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                t["app_name"],
                                t["window_title_hash"],
                                t["start_time"],
                                t["end_time"],
                                t["duration_seconds"],
                                t["keystroke_count"],
                                t["is_password"],
                                t["is_past"],
                                t["source"],
                            ),
                        )

                # Export operation types
                cur = src_conn.execute(
                    "SELECT * FROM operation_types WHERE timestamp >= ? AND timestamp <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for op in cur.fetchall():
                    if op["app_name"].lower() in ex_apps:
                        redacted_operations += 1
                    else:
                        conn.execute(
                            """
                            INSERT INTO operation_types (
                                app_name, operation_type, timestamp, is_past, source
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                op["app_name"],
                                op["operation_type"],
                                op["timestamp"],
                                op["is_past"],
                                op["source"],
                            ),
                        )

                # Export clipboard transfers
                cur = src_conn.execute(
                    "SELECT * FROM clipboard_transfers WHERE copy_time >= ? AND copy_time <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for cb in cur.fetchall():
                    src_excluded = cb["source_app"].lower() in ex_apps
                    tgt_excluded = (
                        cb["target_app"].lower() in ex_apps if cb["target_app"] else False
                    )
                    if src_excluded or tgt_excluded:
                        redacted_clipboard += 1
                    else:
                        conn.execute(
                            """
                            INSERT INTO clipboard_transfers (
                                source_app, target_app, data_type, data_length,
                                copy_time, paste_time, is_past, source
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                cb["source_app"],
                                cb["target_app"],
                                cb["data_type"],
                                cb["data_length"],
                                cb["copy_time"],
                                cb["paste_time"],
                                cb["is_past"],
                                cb["source"],
                            ),
                        )

                # Export control events
                cur = src_conn.execute(
                    "SELECT * FROM control_events WHERE timestamp >= ? AND timestamp <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for ce in cur.fetchall():
                    if ce["app_name"].lower() in ex_apps:
                        redacted_control += 1
                    else:
                        conn.execute(
                            """
                            INSERT INTO control_events (
                                app_name, window_title_hash, event_type, control_type,
                                automation_id, class_name, framework_id, state,
                                browser_domain, timestamp, is_past, source
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                ce["app_name"],
                                ce["window_title_hash"],
                                ce["event_type"],
                                ce["control_type"],
                                ce["automation_id"],
                                ce["class_name"],
                                ce["framework_id"],
                                ce["state"],
                                ce["browser_domain"],
                                ce["timestamp"],
                                ce["is_past"],
                                ce["source"],
                            ),
                        )

                # Export existing excluded intervals
                cur = src_conn.execute(
                    "SELECT * FROM excluded_intervals WHERE end_time >= ? AND start_time <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for ex in cur.fetchall():
                    conn.execute(
                        """
                        INSERT INTO excluded_intervals (
                            start_time, end_time, duration_seconds, reason
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (ex["start_time"], ex["end_time"], ex["duration_seconds"], ex["reason"]),
                    )

                # Export system events
                cur = src_conn.execute(
                    "SELECT * FROM system_events WHERE timestamp >= ? AND timestamp <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for se in cur.fetchall():
                    conn.execute(
                        """
                        INSERT INTO system_events (event_type, timestamp, is_past, source)
                        VALUES (?, ?, ?, ?)
                        """,
                        (se["event_type"], se["timestamp"], se["is_past"], se["source"]),
                    )

                # Export file events
                cur = src_conn.execute(
                    "SELECT * FROM file_events WHERE timestamp >= ? AND timestamp <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for fe in cur.fetchall():
                    if fe["app_name"] and fe["app_name"].lower() in ex_apps:
                        pass
                    else:
                        conn.execute(
                            """
                            INSERT INTO file_events (
                                app_name, file_hash, file_ext, timestamp, is_past, source
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                fe["app_name"],
                                fe["file_hash"],
                                fe["file_ext"],
                                fe["timestamp"],
                                fe["is_past"],
                                fe["source"],
                            ),
                        )

                # Export browser events
                cur = src_conn.execute(
                    "SELECT * FROM browser_events WHERE timestamp >= ? AND timestamp <= ?",
                    (start.isoformat(), end.isoformat()),
                )
                for be in cur.fetchall():
                    conn.execute(
                        """
                        INSERT INTO browser_events (browser_domain, timestamp, is_past, source)
                        VALUES (?, ?, ?, ?)
                        """,
                        (be["browser_domain"], be["timestamp"], be["is_past"], be["source"]),
                    )
            finally:
                src_conn.close()

            conn.commit()
        finally:
            conn.close()

        total_redacted = (
            redacted_sessions
            + redacted_typing
            + redacted_operations
            + redacted_clipboard
            + redacted_control
        )
        return {
            "excluded_apps_count": len(ex_apps),
            "redacted_sessions": redacted_sessions,
            "redacted_typing_activities": redacted_typing,
            "redacted_operation_types": redacted_operations,
            "redacted_clipboard_transfers": redacted_clipboard,
            "redacted_control_events": redacted_control,
            "total_redacted_records": total_redacted,
        }

    def delete_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> None:
        """Deletes records across all tables within the given time range,

        then reclaims database disk space via VACUUM.
        """
        conn = self._connect()
        try:
            if start is None and end is None:
                conn.execute("DELETE FROM app_sessions")
                conn.execute("DELETE FROM typing_activities")
                conn.execute("DELETE FROM operation_types")
                conn.execute("DELETE FROM clipboard_transfers")
                conn.execute("DELETE FROM control_events")
                conn.execute("DELETE FROM excluded_intervals")
                conn.execute("DELETE FROM system_events")
                conn.execute("DELETE FROM file_events")
                conn.execute("DELETE FROM browser_events")
            else:
                s_iso = start.isoformat() if start else "-9999-01-01"
                e_iso = end.isoformat() if end else "9999-12-31"

                conn.execute(
                    "DELETE FROM app_sessions WHERE end_time >= ? AND start_time <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM typing_activities WHERE end_time >= ? AND start_time <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM operation_types WHERE timestamp >= ? AND timestamp <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM clipboard_transfers WHERE copy_time >= ? AND copy_time <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM control_events WHERE timestamp >= ? AND timestamp <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM excluded_intervals WHERE end_time >= ? AND start_time <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM system_events WHERE timestamp >= ? AND timestamp <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM file_events WHERE timestamp >= ? AND timestamp <= ?",
                    (s_iso, e_iso),
                )
                conn.execute(
                    "DELETE FROM browser_events WHERE timestamp >= ? AND timestamp <= ?",
                    (s_iso, e_iso),
                )
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

        # Reclaim disk space via VACUUM
        try:
            vacuum_conn = sqlite3.connect(str(self.db_path), isolation_level=None)
            try:
                vacuum_conn.execute("VACUUM")
                vacuum_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                vacuum_conn.close()
        except sqlite3.OperationalError:
            pass

    def delete_before(self, cutoff: datetime) -> None:
        """Deletes records older than cutoff across all tables."""
        c_iso = cutoff.isoformat()
        conn = self._connect()
        try:
            conn.execute("DELETE FROM app_sessions WHERE end_time < ?", (c_iso,))
            conn.execute("DELETE FROM typing_activities WHERE end_time < ?", (c_iso,))
            conn.execute("DELETE FROM operation_types WHERE timestamp < ?", (c_iso,))
            conn.execute("DELETE FROM clipboard_transfers WHERE copy_time < ?", (c_iso,))
            conn.execute("DELETE FROM control_events WHERE timestamp < ?", (c_iso,))
            conn.execute("DELETE FROM excluded_intervals WHERE end_time < ?", (c_iso,))
            conn.execute("DELETE FROM system_events WHERE timestamp < ?", (c_iso,))
            conn.execute("DELETE FROM file_events WHERE timestamp < ?", (c_iso,))
            conn.execute("DELETE FROM browser_events WHERE timestamp < ?", (c_iso,))
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

        try:
            vacuum_conn = sqlite3.connect(str(self.db_path), isolation_level=None)
            try:
                vacuum_conn.execute("VACUUM")
                vacuum_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                vacuum_conn.close()
        except sqlite3.OperationalError:
            pass
