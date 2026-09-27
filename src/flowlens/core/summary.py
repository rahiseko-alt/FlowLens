import sqlite3
from pathlib import Path
from typing import Any


def generate_summary(db_path: str | Path) -> dict[str, Any]:
    """Generates summary statistics (app durations, session counts, transfers)

    separated by live and past records directly from the exported SQLite database.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # Total active seconds across all app sessions
        cur.execute("SELECT COALESCE(SUM(duration_seconds), 0.0) FROM app_sessions")
        total_active_seconds = float(cur.fetchone()[0])

        live_apps: dict[str, dict[str, Any]] = {}
        past_apps: dict[str, dict[str, Any]] = {}
        live_total_seconds = 0.0
        past_total_seconds = 0.0

        # Query session statistics grouped by app and is_past
        cur.execute(
            """
            SELECT app_name, is_past, SUM(duration_seconds) as total_dur, COUNT(*) as cnt
            FROM app_sessions
            GROUP BY app_name, is_past
            ORDER BY total_dur DESC
            """
        )
        for row in cur.fetchall():
            app = row["app_name"]
            is_past = row["is_past"]
            dur = float(row["total_dur"])
            cnt = int(row["cnt"])
            info = {
                "duration_seconds": dur,
                "session_count": cnt,
            }
            if is_past == 1:
                past_apps[app] = info
                past_total_seconds += dur
            else:
                live_apps[app] = info
                live_total_seconds += dur

        live_transfers: dict[str, int] = {}
        past_transfers: dict[str, int] = {}

        # Query clipboard transfers grouped by source->target and is_past
        cur.execute(
            """
            SELECT source_app, target_app, is_past, COUNT(*) as cnt
            FROM clipboard_transfers
            WHERE source_app IS NOT NULL AND source_app != ''
              AND target_app IS NOT NULL AND target_app != ''
            GROUP BY source_app, target_app, is_past
            ORDER BY cnt DESC
            """
        )
        for row in cur.fetchall():
            key = f"{row['source_app']}->{row['target_app']}"
            cnt = int(row["cnt"])
            if row["is_past"] == 1:
                past_transfers[key] = cnt
            else:
                live_transfers[key] = cnt

        return {
            "total_active_seconds": total_active_seconds,
            "live": {
                "total_seconds": live_total_seconds,
                "apps": live_apps,
                "transfers": live_transfers,
            },
            "past": {
                "total_seconds": past_total_seconds,
                "apps": past_apps,
                "transfers": past_transfers,
            },
        }
    finally:
        conn.close()
