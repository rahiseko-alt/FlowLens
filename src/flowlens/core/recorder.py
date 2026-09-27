"""Recorder: the single public face of the Collector core.

Windows entry points hand raw observations to `observe` and `import_past_providers`;
settings, deletion and export also go through here. Everything that decides what
may be stored (sanitizing, exclusion, pause, hashing) happens in this module, so it
works the same on any OS and is covered by the tests.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any

from flowlens.core import sanitize
from flowlens.core.config import DEFAULT_IDLE_THRESHOLD_SECONDS, ConfigManager
from flowlens.core.crypto import KeyManager
from flowlens.core.export import write_export
from flowlens.core.models import (
    ClipboardObservation,
    ControlMetadataObservation,
    IdleObservation,
    LockObservation,
    Observation,
    OperationTypeObservation,
    PastAppStatsObservation,
    PastBrowserObservation,
    PastFileObservation,
    PastSystemEventObservation,
    SessionDisconnectObservation,
    SleepObservation,
    TimeRange,
    TypingObservation,
    WindowObservation,
)
from flowlens.core.storage import Storage

PAST_IMPORT_DAYS = 30
RETENTION_CHECK_INTERVAL = timedelta(hours=1)
BLACKOUT_MEMORY = timedelta(days=1)
TMP_PREFIX = "flowlens-tmp-"
EXPORT_PRESETS = {"last_7_days": 7, "last_14_days": 14, "last_30_days": 30}
DELETE_PRESETS = {"last_7_days": 7, "last_30_days": 30}

_AWAY_TYPES = {
    IdleObservation: "is_idle",
    LockObservation: "is_locked",
    SleepObservation: "is_asleep",
    SessionDisconnectObservation: "is_disconnected",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Recorder:
    """Thread-safe: observation threads and the UI thread may call it concurrently."""

    def __init__(
        self,
        storage_dir: str | Path,
        clock: Callable[[], datetime] | None = None,
        local_tz: tzinfo | None = None,
    ):
        """`local_tz` decides what "today" means for deletion; None = the PC's time zone."""
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "collector.db"
        self.storage = Storage(self.db_path)
        self._keys = KeyManager(self.storage_dir)
        self._config = ConfigManager(self.storage_dir)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.local_tz = local_tz
        self._lock = threading.RLock()

        self._away: set[type] = set()
        self._session: dict[str, Any] | None = None  # the open App Session
        self._pending_copy: dict[str, Any] | None = None
        self._last_retention_check: datetime | None = None
        # Pauses and absences seen by this process, as [start, end or None]. Observations
        # that arrive late but are stamped inside one of them are dropped.
        self._blackouts: list[list[datetime | None]] = []
        paused_since = self._config.get("paused_since")
        if paused_since:
            self._blackouts.append([datetime.fromisoformat(paused_since), None])

    def remove_leftover_temp_files(self) -> None:
        """Deletes plain copies left by an export or import that was cut short.

        Call only from the one running collector (after taking the single-instance lock).
        """
        for leftover in self.storage_dir.glob(f"{TMP_PREFIX}*"):
            shutil.rmtree(leftover, ignore_errors=True)

    # ------------------------------------------------------------------ settings

    @property
    def is_paused(self) -> bool:
        return self._config.get("paused_since") is not None

    def pause(self, timestamp: datetime | None = None) -> None:
        with self._lock:
            if self.is_paused:
                return
            self.flush()
            start = _utc(timestamp or self.clock())
            self._config.set("paused_since", start.isoformat())
            self._blackouts.append([start, None])

    def resume(self, timestamp: datetime | None = None) -> None:
        with self._lock:
            since = self._config.get("paused_since")
            if since is None:
                return
            end = _utc(timestamp or self.clock())
            self._config.set("paused_since", None)
            self._end_blackout(end)
            self._insert_interval(datetime.fromisoformat(since), end, "pause")

    @property
    def user_exited(self) -> bool:
        """True after the employee chose 終了 until the next login (read by the watchdog)."""
        return bool(self._config.get("user_exited"))

    @user_exited.setter
    def user_exited(self, value: bool) -> None:
        self._config.set("user_exited", bool(value))

    @property
    def idle_threshold_seconds(self) -> float:
        value = self._config.get("idle_threshold_seconds")
        return float(value) if value else DEFAULT_IDLE_THRESHOLD_SECONDS

    def set_idle_threshold_seconds(self, seconds: float) -> None:
        if seconds <= 0:
            raise ValueError("The idle threshold must be positive.")
        self._config.set("idle_threshold_seconds", float(seconds))

    def get_excluded_apps(self) -> list[str]:
        return sorted(self._config.get("excluded_apps") or [])

    def add_excluded_app(self, app: str) -> None:
        name, ok = sanitize.app_name(app)
        if not name or not ok:
            raise ValueError(f"Not an application name: {app!r} (example: slack.exe)")
        with self._lock:
            apps = set(self.get_excluded_apps()) | {name}
            self._config.set("excluded_apps", sorted(apps))
            if self._session and self._session["app"] == name:
                self._session["title_symbol"] = self._session["title_ext"] = ""

    def remove_excluded_app(self, app: str) -> None:
        name, _ = sanitize.app_name(app)
        with self._lock:
            self._config.set("excluded_apps", [a for a in self.get_excluded_apps() if a != name])

    def _is_excluded(self, app: str | None) -> bool:
        return bool(app) and app in set(self.get_excluded_apps())

    def get_retention_days(self) -> int | None:
        return self._config.get("retention_days")

    def set_retention_days(self, days: int | None) -> None:
        if days is not None and days not in (30, 60, 90):
            raise ValueError("Retention must be 30, 60, 90 days or None (keep forever).")
        with self._lock:
            self._config.set("retention_days", days)
            self._last_retention_check = None
            self._apply_retention_if_due()

    def get_enabled_past_sources(self) -> list[str] | None:
        return self._config.get("enabled_past_sources")

    def set_enabled_past_sources(self, sources: Iterable[str] | None) -> None:
        self._config.set("enabled_past_sources", None if sources is None else sorted(set(sources)))

    def is_past_source_enabled(self, source: str) -> bool:
        enabled = self.get_enabled_past_sources()
        return enabled is None or source in enabled

    # ------------------------------------------------------------------ live capture

    def observe(self, observation: Observation) -> None:
        with self._lock:
            self._apply_retention_if_due()
            obs_type = type(observation)
            if obs_type in _AWAY_TYPES:
                # Tracked even while paused, so an unlock during a pause is not missed.
                self._handle_away(observation, getattr(observation, _AWAY_TYPES[obs_type]))
                return
            if self.is_paused or self._away:
                return  # nothing is recorded while paused, idle, locked, asleep or disconnected
            if self._in_blackout(observation):
                return  # arrived late, but happened during a pause or an absence
            handler = {
                WindowObservation: self._handle_window,
                TypingObservation: self._handle_typing,
                OperationTypeObservation: self._handle_operation,
                ClipboardObservation: self._handle_clipboard,
                ControlMetadataObservation: self._handle_control,
            }.get(obs_type)
            if handler:
                handler(observation)

    def _app(self, raw: str | None) -> str:
        """Sanitized app name; falls back to the foreground app of the open session."""
        if raw:
            name, ok = sanitize.app_name(raw)
            return name if ok else "other"
        return self._session["app"] if self._session else "other"

    def _title_symbol(self) -> str:
        return self._session["title_symbol"] if self._session else ""

    def _handle_away(self, obs: Observation, away: bool) -> None:
        kind = type(obs)
        when = _utc(obs.timestamp)
        if away:
            if not self._away:
                # The session ends when the absence began (for idle: the last input).
                self._close_session(when)
                self._blackouts.append([when, None])
            self._away.add(kind)
        elif kind in self._away:
            self._away.discard(kind)
            if not self._away:
                self._end_blackout(when)

    def _end_blackout(self, when: datetime) -> None:
        for blackout in self._blackouts:
            if blackout[1] is None:
                blackout[1] = max(when, blackout[0])
        horizon = when - BLACKOUT_MEMORY
        self._blackouts = [b for b in self._blackouts if b[1] is None or b[1] > horizon]

    def _in_blackout(self, obs: Observation) -> bool:
        start = _utc(obs.timestamp)
        end = start + timedelta(seconds=max(0.0, getattr(obs, "duration_seconds", 0.0)))
        return any(
            start < (b_end or datetime.max.replace(tzinfo=timezone.utc)) and end >= b_start
            for b_start, b_end in self._blackouts
        )

    def _handle_window(self, obs: WindowObservation) -> None:
        now = _utc(obs.timestamp)
        app = self._app(obs.app_name)
        if self._is_excluded(app):
            symbol, ext = "", ""
        else:
            symbol = self._keys.symbol(obs.window_title)
            ext = sanitize.file_extension(obs.window_title)
        s = self._session
        if s is not None:
            gap = (now - s["last_seen"]).total_seconds()
            if gap > self.idle_threshold_seconds:
                # No observation for longer than the idle threshold: we were not watching.
                self._close_session(s["last_seen"])
            elif s["app"] == app and s["title_symbol"] == symbol:
                s["last_seen"] = now
                return
            else:
                self._close_session(now)
        self._session = {
            "app": app,
            "title_symbol": symbol,
            "title_ext": ext,
            "start": now,
            "last_seen": now,
        }

    def _close_session(self, end: datetime) -> None:
        s, self._session = self._session, None
        if s is None:
            return
        end = max(end, s["start"])
        if self._is_excluded(s["app"]):
            self._insert_interval(s["start"], end, "excluded_app")
            return
        duration = (end - s["start"]).total_seconds()
        if duration > 0:
            self.storage.insert(
                "app_sessions",
                {
                    "app_name": s["app"],
                    "title_symbol": s["title_symbol"],
                    "title_ext": s["title_ext"],
                    "start_time": s["start"],
                    "end_time": end,
                    "duration_seconds": duration,
                    "is_past": 0,
                    "source": "live",
                },
            )

    def _insert_interval(self, start: datetime, end: datetime, reason: str) -> None:
        duration = (end - start).total_seconds()
        if duration > 0:
            self.storage.insert(
                "excluded_intervals",
                {
                    "start_time": start,
                    "end_time": end,
                    "duration_seconds": duration,
                    "reason": reason,
                },
            )

    def _handle_typing(self, obs: TypingObservation) -> None:
        app = self._app(obs.app_name)
        if self._is_excluded(app):
            return
        start = _utc(obs.timestamp)
        duration = max(0.0, obs.duration_seconds)
        self.storage.insert(
            "typing_activities",
            {
                "app_name": app,
                "title_symbol": self._title_symbol(),
                "start_time": start,
                "end_time": start + timedelta(seconds=duration),
                "duration_seconds": duration,
                # In a password field only the fact remains, not even the count.
                "keystroke_count": 0 if obs.is_password else max(0, obs.keystrokes),
                "is_password": obs.is_password,
                "is_past": 0,
                "source": "live",
            },
        )

    def _handle_operation(self, obs: OperationTypeObservation) -> None:
        app = self._app(obs.app_name)
        op = sanitize.choice(obs.operation_type, sanitize.OPERATION_TYPES)
        if not op or self._is_excluded(app) or obs.in_password:
            if op == "ctrl+v":
                self._pending_copy = None  # pasted into an excluded app: forget the copy
            return
        now = _utc(obs.timestamp)
        self.storage.insert(
            "operation_events",
            {
                "app_name": app,
                "operation_type": op,
                "timestamp": now,
                "is_past": 0,
                "source": "live",
            },
        )
        if op == "ctrl+v":
            self._finish_transfer(app, now)

    def _handle_clipboard(self, obs: ClipboardObservation) -> None:
        action = sanitize.choice(obs.action, sanitize.CLIPBOARD_ACTIONS)
        app = self._app(obs.app_name)
        now = _utc(obs.timestamp)
        if action == "paste":
            if self._is_excluded(app) or obs.in_password:
                self._pending_copy = None
            else:
                self._finish_transfer(app, now)
            return
        if not action:
            return
        self._finish_transfer("", None)  # a copy that was never pasted
        if self._is_excluded(app):
            return
        self._pending_copy = {
            "action": action,
            "source_app": app,
            "data_type": sanitize.choice(obs.data_type, sanitize.CLIPBOARD_DATA_TYPES, "other"),
            "data_length": max(0, int(obs.data_length)),
            "copy_time": now,
        }

    def _finish_transfer(self, target_app: str, paste_time: datetime | None) -> None:
        pending, self._pending_copy = self._pending_copy, None
        if pending is None:
            return
        self.storage.insert(
            "clipboard_transfers",
            {
                **pending,
                "target_app": target_app,
                "paste_time": paste_time,
                "is_past": 0,
                "source": "live",
            },
        )

    def _handle_control(self, obs: ControlMetadataObservation) -> None:
        app = self._app(obs.app_name)
        event = sanitize.choice(obs.event_type, sanitize.CONTROL_EVENT_TYPES)
        if not event or self._is_excluded(app):
            return
        self.storage.insert(
            "control_events",
            {
                "app_name": app,
                "title_symbol": self._title_symbol(),
                "event_type": event,
                "control_type": sanitize.identifier(obs.control_type),
                "automation_id": sanitize.identifier(obs.automation_id),
                "class_name": sanitize.identifier(obs.class_name),
                "framework_id": sanitize.identifier(obs.framework_id),
                "state": sanitize.choice(obs.state, sanitize.CONTROL_STATES),
                "browser_domain": sanitize.domain(obs.browser_domain),
                "timestamp": _utc(obs.timestamp),
                "is_past": 0,
                "source": "live",
            },
        )

    def flush(self) -> None:
        """Writes the open session and any unpasted copy (e.g. before export or exit)."""
        with self._lock:
            if self._session is not None:
                self._close_session(self._session["last_seen"])
            self._finish_transfer("", None)

    # ------------------------------------------------------------------ past import

    def import_past_providers(
        self, providers: dict[str, Callable[[], list[Any]]]
    ) -> dict[str, dict[str, Any]]:
        """Runs each selected source independently; one failure never stops the others."""
        report: dict[str, dict[str, Any]] = {}
        for source, provider in providers.items():
            if self.is_paused:
                result = {"status": "skipped", "count": 0, "error": "paused"}
            elif not self.is_past_source_enabled(source):
                result = {"status": "skipped", "count": 0, "error": "not selected"}
            else:
                try:
                    records, warning = _split_warning(provider())
                    count = self._import_records(source, records)
                    result = {
                        "status": "partial" if warning else "success",
                        "count": count,
                        "error": sanitize.error_code(warning) or None if warning else None,
                    }
                except Exception as exc:  # the reason is kept as a code, never a message
                    result = {"status": "failed", "count": 0, "error": _error_code(exc)}
            report[source] = result
            if result["status"] != "skipped":
                self.storage.insert(
                    "past_import_runs",
                    {
                        "source": source,
                        "run_at": self.clock(),
                        "status": result["status"],
                        "record_count": result["count"],
                        "error": result["error"],
                    },
                )
        return report

    def _import_records(self, source: str, records: Iterable[Any]) -> int:
        cutoff = _utc(self.clock()) - timedelta(days=PAST_IMPORT_DAYS)
        batches: dict[str, list[dict[str, Any]]] = {}
        with self._lock:  # settings (exclusions) must not change while rows are built
            for record in records:
                row = self._past_row(record, source, cutoff)
                if row is not None:
                    batches.setdefault(row[0], []).append(row[1])
        inserted = 0
        for table, rows in batches.items():
            if table == "past_app_stats":
                inserted += self.storage.upsert_many(table, rows)
            else:
                inserted += self.storage.insert_many(table, rows)
        return inserted

    def _past_row(
        self, record: Any, source: str, cutoff: datetime
    ) -> tuple[str, dict[str, Any]] | None:
        common = {"is_past": 1, "source": source}
        if isinstance(record, PastSystemEventObservation):
            event = sanitize.choice(record.event_type, sanitize.SYSTEM_EVENT_TYPES)
            when = _utc(record.timestamp)
            if not event or when < cutoff:
                return None
            return "system_events", {"event_type": event, "timestamp": when, **common}
        if isinstance(record, PastAppStatsObservation):
            when = _utc(record.last_used)
            app = self._app(record.app_name)
            if when < cutoff or app == "other" or self._is_excluded(app):
                return None
            return "past_app_stats", {
                "app_name": app,
                "last_used": when,
                "run_count": max(0, record.run_count),
                "focus_seconds": max(0.0, record.focus_seconds),
                **common,
            }
        if isinstance(record, PastFileObservation):
            when = _utc(record.timestamp)
            app = self._app(record.app_name) if record.app_name else ""
            if when < cutoff or not record.file_name or self._is_excluded(app):
                return None
            name = record.file_name.replace("\\", "/").rsplit("/", 1)[-1]
            return "file_events", {
                "app_name": app,
                "file_symbol": self._keys.symbol(name),
                "file_ext": sanitize.file_extension(name),
                "timestamp": when,
                **common,
            }
        if isinstance(record, PastBrowserObservation):
            when = _utc(record.timestamp)
            app = self._app(record.app_name) if record.app_name else ""
            host = sanitize.domain(record.domain)
            if when < cutoff or not host or self._is_excluded(app):
                return None
            return "browser_events", {"app_name": app, "domain": host, "timestamp": when, **common}
        return None

    # ------------------------------------------------------------------ retention, deletion

    def _apply_retention_if_due(self) -> None:
        now = _utc(self.clock())
        last = self._last_retention_check
        if last is not None and now - last < RETENTION_CHECK_INTERVAL:
            return
        self._last_retention_check = now
        days = self.get_retention_days()
        if days:
            self.storage.delete_before(now - timedelta(days=days))

    def delete(self, target: TimeRange | str) -> None:
        """Deletes 'today' (local calendar day), 'last_7_days', 'last_30_days', 'all' or a range."""
        with self._lock:
            self.flush()
            now = _utc(self.clock())
            if isinstance(target, TimeRange):
                self.storage.delete_range(_utc(target.start), _utc(target.end))
            elif target == "all":
                self.storage.delete_range(None, None)
            elif target == "today":
                local = now.astimezone(self.local_tz)
                midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
                self.storage.delete_range(midnight.astimezone(timezone.utc), None)
            elif target in DELETE_PRESETS:
                self.storage.delete_range(now - timedelta(days=DELETE_PRESETS[target]), None)
            else:
                raise ValueError(f"Unknown deletion scope: {target}")

    # ------------------------------------------------------------------ export

    def compute_export_range(
        self, preset: str, start: datetime | None = None, end: datetime | None = None
    ) -> TimeRange:
        now = _utc(self.clock())
        if preset in EXPORT_PRESETS:
            return TimeRange(now - timedelta(days=EXPORT_PRESETS[preset]), now)
        if preset == "all":
            return TimeRange(datetime(2000, 1, 1, tzinfo=timezone.utc), now)
        if preset == "custom":
            if start is None or end is None:
                raise ValueError("A custom range needs a start and an end.")
            return TimeRange(_utc(start), _utc(end))
        raise ValueError(f"Unknown export range preset: {preset}")

    def export(self, time_range: TimeRange, password: str, destination: str | Path) -> Path:
        """Writes the encrypted Diagnostic Export and returns its path.

        The App Session still in progress is not part of it; it is written when it ends.
        """
        with self._lock:
            created = _utc(self.clock())
            start, end = _utc(time_range.start), _utc(time_range.end)
            count = write_export(
                self.storage,
                start=start,
                end=end,
                excluded_apps=set(self.get_excluded_apps()),
                password=password,
                destination=Path(destination),
                device_id=self._keys.get_device_id(),
                created_at=created,
                work_dir=self.storage_dir,
                tmp_prefix=TMP_PREFIX,
            )
            self.storage.record_export(created, start, end, count)
            return Path(destination)

    # ------------------------------------------------------------------ status

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            stats = self.storage.live_stats()
            if self._session is not None:
                s = self._session
                stats["live_seconds"] += (s["last_seen"] - s["start"]).total_seconds()
            size = sum(
                p.stat().st_size for p in (self.db_path, Path(f"{self.db_path}-wal")) if p.exists()
            )
            return {
                "is_recording": not self.is_paused,
                "is_paused": self.is_paused,
                "first_live_session": stats["first_live_session"],
                "recorded_seconds": stats["live_seconds"],
                "session_count": stats["live_session_count"],
                "database_size_bytes": size,
            }


def _split_warning(result: Any) -> tuple[Any, str | None]:
    """A provider may return (records, warning) when only part of a source was readable."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], (str, type(None))):
        return result[0], result[1]
    return result, None


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    name = type(exc).__name__
    return sanitize.error_code(f"{name} {code}" if code else name) or "error"
