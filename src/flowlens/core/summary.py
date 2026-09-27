"""summary.json: totals computed with SQL only (no AI), live and past kept apart."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def generate_summary(db_path: str | Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:

        def pairs(sql: str) -> dict[str, Any]:
            return {row[0]: row[1] for row in conn.execute(sql)}

        # foreground_switches: how often the app came to the front from another app
        # (a new title in the same app is a new session but not a switch).
        live_apps = {
            app: {"duration_seconds": dur, "session_count": cnt, "foreground_switches": sw}
            for app, dur, cnt, sw in conn.execute(
                "SELECT app_name, SUM(duration_seconds), COUNT(*), "
                "SUM(CASE WHEN prev IS NULL OR prev != app_name THEN 1 ELSE 0 END) FROM ("
                "  SELECT app_name, duration_seconds, "
                "  LAG(app_name) OVER (ORDER BY start_time) AS prev "
                "  FROM app_sessions WHERE is_past = 0"
                ") GROUP BY app_name ORDER BY SUM(duration_seconds) DESC"
            )
        }
        past_apps = {
            app: {"run_count": runs, "focus_seconds": focus, "last_used": last}
            for app, runs, focus, last in conn.execute(
                "SELECT app_name, SUM(run_count), SUM(focus_seconds), MAX(last_used) "
                "FROM past_app_stats GROUP BY app_name ORDER BY SUM(focus_seconds) DESC"
            )
        }
        return {
            "live": {
                "total_seconds": sum(a["duration_seconds"] for a in live_apps.values()),
                "apps": live_apps,
                "clipboard_transfers": pairs(
                    "SELECT source_app || '->' || target_app, COUNT(*) FROM clipboard_transfers "
                    "WHERE target_app != '' GROUP BY 1 ORDER BY 2 DESC"
                ),
                "keystrokes_by_app": pairs(
                    "SELECT app_name, SUM(keystroke_count) FROM typing_activities "
                    "GROUP BY app_name ORDER BY 2 DESC"
                ),
                "operations": pairs(
                    "SELECT operation_type, COUNT(*) FROM operation_events "
                    "GROUP BY 1 ORDER BY 2 DESC"
                ),
                "excluded_seconds": pairs(
                    "SELECT reason, SUM(duration_seconds) FROM excluded_intervals GROUP BY reason"
                ),
            },
            "past": {
                "app_usage_counters": past_apps,
                "system_events": pairs(
                    "SELECT event_type, COUNT(*) FROM system_events GROUP BY 1 ORDER BY 2 DESC"
                ),
                "file_opens_by_extension": pairs(
                    "SELECT file_ext, COUNT(*) FROM file_events GROUP BY 1 ORDER BY 2 DESC"
                ),
                "top_domains": pairs(
                    "SELECT domain, COUNT(*) FROM browser_events "
                    "GROUP BY 1 ORDER BY 2 DESC LIMIT 50"
                ),
                "sources": {
                    src: {"status": status, "record_count": cnt}
                    for src, status, cnt in conn.execute(
                        "SELECT source, status, record_count FROM past_import_runs ORDER BY run_at"
                    )
                },
            },
        }
    finally:
        conn.close()
