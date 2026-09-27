import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pyzipper

from flowlens.core.config import ConfigManager
from flowlens.core.crypto import KeyManager
from flowlens.core.models import (
    ClipboardObservation,
    ControlMetadataObservation,
    IdleObservation,
    LockObservation,
    Observation,
    OperationTypeObservation,
    PastAppUsageObservation,
    PastBrowserObservation,
    PastFileObservation,
    PastSystemEventObservation,
    SessionDisconnectObservation,
    SleepObservation,
    TimeRange,
    TypingObservation,
    WindowObservation,
)
from flowlens.core.redaction import extract_browser_domain
from flowlens.core.storage import Storage
from flowlens.core.summary import generate_summary

MANIFEST_VERSION = "0.1.0"


class Recorder:
    """The central facade of FlowLens Collector Core.

    All external interactions with FlowLens Core pass through this class.
    """

    def __init__(
        self,
        storage_dir: str | Path,
        clock: Callable[[], datetime] | None = None,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "collector.db"
        self.storage = Storage(self.db_path)
        self.key_manager = KeyManager(self.storage_dir)
        self.config_manager = ConfigManager(self.storage_dir)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

        self._active_app: str | None = None
        self._active_title_hash: str = ""
        self._active_title_ext: str = ""
        self._active_start: datetime | None = None
        self._active_end: datetime | None = None

        self._is_paused = False
        self._pause_start: datetime | None = None
        self._excluded_apps: set[str] = set(self.config_manager.get_excluded_apps())
        self._enabled_past_sources: set[str] | None = None
        self._retention_days: int | None = self.config_manager.get_retention_days()
        self._idle_threshold_seconds: float = 300.0

        self._is_idle = False
        self._is_locked = False
        self._is_asleep = False
        self._is_disconnected = False

        self._pending_copy: dict[str, Any] | None = None

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def idle_threshold_seconds(self) -> float:
        return self._idle_threshold_seconds

    def set_idle_threshold_seconds(self, seconds: float) -> None:
        self._idle_threshold_seconds = seconds

    @property
    def is_away(self) -> bool:
        """Returns True if the system is idle, locked, sleeping, or disconnected."""
        return (
            self._is_idle
            or self._is_locked
            or self._is_asleep
            or self._is_disconnected
        )

    def pause(self, timestamp: datetime | None = None) -> None:
        self.flush()
        self._is_paused = True
        self._pause_start = timestamp or self.clock()

    def resume(self, timestamp: datetime | None = None) -> None:
        if self._is_paused:
            self._is_paused = False
            resume_time = timestamp or self.clock()
            if self._pause_start is not None:
                duration = (resume_time - self._pause_start).total_seconds()
                if duration > 0:
                    self.storage.insert_excluded_interval(
                        start_time=self._pause_start,
                        end_time=resume_time,
                        duration_seconds=duration,
                        reason="pause",
                    )
            self._pause_start = None

    def get_excluded_apps(self) -> list[str]:
        """Returns the list of excluded app names."""
        return sorted(self._excluded_apps)

    def add_excluded_app(self, app_name: str) -> None:
        """Adds an application to the excluded list and persists it."""
        clean = app_name.lower().strip()
        if not clean:
            return
        self._excluded_apps.add(clean)
        self.config_manager.add_excluded_app(clean)

    def remove_excluded_app(self, app_name: str) -> None:
        """Removes an application from the excluded list and persists it."""
        clean = app_name.lower().strip()
        self._excluded_apps.discard(clean)
        self.config_manager.remove_excluded_app(clean)

    def set_excluded_apps(self, apps: list[str]) -> None:
        self._excluded_apps = {app.lower().strip() for app in apps}
        for a in self.config_manager.get_excluded_apps():
            if a not in self._excluded_apps:
                self.config_manager.remove_excluded_app(a)
        for a in self._excluded_apps:
            self.config_manager.add_excluded_app(a)

    def get_retention_days(self) -> int | None:
        """Returns the retention period in days (None means indefinite)."""
        return self._retention_days

    def set_retention_days(self, days: int | None) -> None:
        if days is None or days <= 0:
            self._retention_days = None
        else:
            self._retention_days = int(days)
        self.config_manager.set_retention_days(self._retention_days)

    def apply_retention_policy(self) -> None:
        """Deletes records exceeding retention period.

        If retention is None, records are kept indefinitely.
        """
        if self._retention_days is not None and self._retention_days > 0:
            cutoff = self.clock() - timedelta(days=self._retention_days)
            self.storage.delete_before(cutoff)

    def compute_export_range(
        self,
        preset: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> TimeRange:
        """Computes a TimeRange from a user-facing preset or custom dates."""
        now = self.clock()
        p = preset.lower().strip()
        if p == "last_7_days":
            return TimeRange(start=now - timedelta(days=7), end=now)
        elif p == "last_14_days":
            return TimeRange(start=now - timedelta(days=14), end=now)
        elif p == "last_30_days":
            return TimeRange(start=now - timedelta(days=30), end=now)
        elif p == "all":
            return TimeRange(start=datetime.min.replace(tzinfo=timezone.utc), end=now)
        elif p == "custom":
            if start is None or end is None:
                raise ValueError("Custom range requires both start and end datetimes")
            return TimeRange(start=start, end=end)
        else:
            raise ValueError(f"Unknown export range preset: {preset}")

    def set_enabled_past_sources(self, sources: list[str] | set[str] | None) -> None:
        """Configures which past import sources are allowed to be ingested.

        None means all sources are enabled.
        """
        if sources is None:
            self._enabled_past_sources = None
        else:
            self._enabled_past_sources = {s.lower().strip() for s in sources}

    def is_past_source_enabled(self, source: str) -> bool:
        """Returns True if the given past import source is enabled."""
        if self._enabled_past_sources is None:
            return True
        return source.lower().strip() in self._enabled_past_sources

    def import_past_records(self, source: str, records: list[Any]) -> dict[str, Any]:
        """Imports a list of past records for a specific source, applying privacy sanitization,

        30-day cutoff, app exclusion, and de-duplication.
        """
        if not self.is_past_source_enabled(source):
            return {"status": "skipped", "count": 0, "error": None}

        cutoff = self.clock() - timedelta(days=30)
        inserted_count = 0

        for record in records:
            ts = getattr(record, "timestamp", None) or getattr(record, "start_time", None)
            if ts is not None and ts < cutoff:
                continue

            if isinstance(record, PastAppUsageObservation):
                if record.app_name.lower() in self._excluded_apps:
                    continue
                title_hash, title_ext = self.key_manager.hash_title(record.window_title)
                if self.storage.insert_app_session(
                    app_name=record.app_name,
                    window_title_hash=title_hash,
                    window_title_ext=title_ext,
                    start_time=record.start_time,
                    end_time=record.end_time,
                    duration_seconds=record.duration_seconds,
                    is_past=1,
                    source=record.source or source,
                ):
                    inserted_count += 1

            elif isinstance(record, PastSystemEventObservation):
                if self.storage.insert_system_event(
                    event_type=record.event_type,
                    timestamp=record.timestamp,
                    is_past=1,
                    source=record.source or source,
                ):
                    inserted_count += 1

            elif isinstance(record, PastFileObservation):
                if record.app_name and record.app_name.lower() in self._excluded_apps:
                    continue
                file_name = Path(record.file_path).name
                file_hash, file_ext = self.key_manager.hash_title(file_name)
                if self.storage.insert_file_event(
                    app_name=record.app_name,
                    file_hash=file_hash,
                    file_ext=file_ext,
                    timestamp=record.timestamp,
                    is_past=1,
                    source=record.source or source,
                ):
                    inserted_count += 1

            elif isinstance(record, PastBrowserObservation):
                domain = extract_browser_domain(record.url)
                if self.storage.insert_browser_event(
                    browser_domain=domain,
                    timestamp=record.timestamp,
                    is_past=1,
                    source=record.source or source,
                ):
                    inserted_count += 1

        return {"status": "success", "count": inserted_count, "error": None}

    def import_past_providers(
        self, providers: dict[str, Callable[[], list[Any]]]
    ) -> dict[str, dict[str, Any]]:
        """Imports records from multiple source providers.

        Failure in one provider does not interrupt other providers.
        """
        report: dict[str, dict[str, Any]] = {}
        for source, provider in providers.items():
            if not self.is_past_source_enabled(source):
                report[source] = {"status": "skipped", "count": 0, "error": None}
                continue
            try:
                records = provider()
                res = self.import_past_records(source, records)
                report[source] = res
            except Exception as e:
                report[source] = {"status": "failed", "count": 0, "error": str(e)}
        return report

    def observe(self, observation: Observation) -> None:
        """Receive an observation from observation sources."""
        if self._is_paused:
            return

        if isinstance(observation, IdleObservation):
            self._handle_idle_observation(observation)
        elif isinstance(observation, LockObservation):
            self._handle_lock_observation(observation)
        elif isinstance(observation, SleepObservation):
            self._handle_sleep_observation(observation)
        elif isinstance(observation, SessionDisconnectObservation):
            self._handle_disconnect_observation(observation)
        elif isinstance(observation, TypingObservation):
            self._handle_typing_observation(observation)
        elif isinstance(observation, OperationTypeObservation):
            self._handle_operation_observation(observation)
        elif isinstance(observation, ClipboardObservation):
            self._handle_clipboard_observation(observation)
        elif isinstance(observation, ControlMetadataObservation):
            self._handle_control_metadata_observation(observation)
        elif isinstance(observation, WindowObservation):
            self._handle_window_observation(observation)

    def _handle_control_metadata_observation(
        self, obs: ControlMetadataObservation
    ) -> None:
        if self.is_away:
            return

        app_name = obs.app_name or self._active_app or "Unknown"
        if app_name.lower() in self._excluded_apps:
            return

        title_hash = self._active_title_hash
        domain = extract_browser_domain(obs.url)

        self.storage.insert_control_event(
            app_name=app_name,
            window_title_hash=title_hash,
            event_type=obs.event_type,
            control_type=obs.control_type,
            automation_id=obs.automation_id,
            class_name=obs.class_name,
            framework_id=obs.framework_id,
            state=obs.state,
            browser_domain=domain,
            timestamp=obs.timestamp,
            is_past=0,
            source="live",
        )

    def _handle_typing_observation(self, obs: TypingObservation) -> None:
        if self.is_away:
            return

        app_name = obs.app_name or self._active_app or "Unknown"
        if app_name.lower() in self._excluded_apps:
            return

        title_hash = self._active_title_hash
        start_time = obs.timestamp
        duration = max(0.0, obs.duration_seconds)
        end_time = obs.timestamp

        # When in password field, keystroke count is 0 (duration only is preserved)
        keystroke_count = 0 if obs.is_password else obs.keystrokes

        self.storage.insert_typing_activity(
            app_name=app_name,
            window_title_hash=title_hash,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            keystroke_count=keystroke_count,
            is_password=1 if obs.is_password else 0,
            is_past=0,
            source="live",
        )

    def _handle_operation_observation(self, obs: OperationTypeObservation) -> None:
        if self.is_away:
            return

        op = obs.operation_type.lower()
        app_name = obs.app_name or self._active_app or "Unknown"
        if app_name.lower() in self._excluded_apps:
            return

        self.storage.insert_operation_type(
            app_name=app_name,
            operation_type=op,
            timestamp=obs.timestamp,
            is_past=0,
            source="live",
        )

        # If ctrl+v and there is a pending copy, infer paste and complete clipboard transfer
        if op == "ctrl+v" and self._pending_copy:
            self._complete_clipboard_transfer(
                target_app=app_name,
                paste_time=obs.timestamp,
            )

    def _handle_clipboard_observation(self, obs: ClipboardObservation) -> None:
        if self.is_away:
            return

        action = obs.action.lower()
        app_name = obs.app_name or self._active_app or "Unknown"
        if app_name.lower() in self._excluded_apps:
            return

        if action in ("copy", "cut"):
            # If there was a previous unpasted copy, commit it with empty target_app
            if self._pending_copy:
                self._complete_clipboard_transfer(target_app="", paste_time=None)

            self._pending_copy = {
                "source_app": app_name,
                "data_type": obs.data_type,
                "data_length": obs.data_length,
                "copy_time": obs.timestamp,
            }
        elif action == "paste":
            if self._pending_copy:
                self._complete_clipboard_transfer(
                    target_app=app_name,
                    paste_time=obs.timestamp,
                )

    def _complete_clipboard_transfer(
        self, target_app: str, paste_time: datetime | None
    ) -> None:
        if not self._pending_copy:
            return
        source_app = self._pending_copy["source_app"]
        if (
            source_app.lower() in self._excluded_apps
            or target_app.lower() in self._excluded_apps
        ):
            self._pending_copy = None
            return

        self.storage.insert_clipboard_transfer(
            source_app=source_app,
            target_app=target_app,
            data_type=self._pending_copy["data_type"],
            data_length=self._pending_copy["data_length"],
            copy_time=self._pending_copy["copy_time"],
            paste_time=paste_time,
            is_past=0,
            source="live",
        )
        self._pending_copy = None

    def _handle_idle_observation(self, obs: IdleObservation) -> None:
        if obs.is_idle:
            if not self._is_idle:
                self._is_idle = True
                self._commit_active_session(end_time=obs.timestamp)
        else:
            self._is_idle = False

    def _handle_lock_observation(self, obs: LockObservation) -> None:
        if obs.is_locked:
            if not self._is_locked:
                self._is_locked = True
                self._commit_active_session(end_time=obs.timestamp)
        else:
            self._is_locked = False

    def _handle_sleep_observation(self, obs: SleepObservation) -> None:
        if obs.is_asleep:
            if not self._is_asleep:
                self._is_asleep = True
                self._commit_active_session(end_time=obs.timestamp)
        else:
            self._is_asleep = False

    def _handle_disconnect_observation(self, obs: SessionDisconnectObservation) -> None:
        if obs.is_disconnected:
            if not self._is_disconnected:
                self._is_disconnected = True
                self._commit_active_session(end_time=obs.timestamp)
        else:
            self._is_disconnected = False

    def _handle_window_observation(self, obs: WindowObservation) -> None:
        if self.is_away:
            return

        app_name = obs.app_name
        timestamp = obs.timestamp
        if app_name.lower() in self._excluded_apps:
            title_hash = ""
            title_ext = ""
        else:
            title_hash, title_ext = self.key_manager.hash_title(obs.window_title)

        if self._active_app is None:
            # First observation
            self._active_app = app_name
            self._active_title_hash = title_hash
            self._active_title_ext = title_ext
            self._active_start = timestamp
            self._active_end = timestamp
            return

        # Check if switched app or window title
        if app_name != self._active_app or title_hash != self._active_title_hash:
            # If gap between last observation of active app and new observation is > 1 hour,
            # previous session ended at its last observation time.
            if self._active_end and (timestamp - self._active_end).total_seconds() > 3600:
                self._commit_active_session(end_time=self._active_end)
            else:
                self._commit_active_session(end_time=timestamp)
            self._active_app = app_name
            self._active_title_hash = title_hash
            self._active_title_ext = title_ext
            self._active_start = timestamp
            self._active_end = timestamp
        else:
            # Same app and same window
            self._active_end = timestamp

    def _commit_active_session(self, end_time: datetime | None = None) -> None:
        if self._active_app is None or self._active_start is None:
            return

        final_end = end_time or self._active_end or self._active_start
        duration = (final_end - self._active_start).total_seconds()
        if duration > 0:
            if self._active_app.lower() in self._excluded_apps:
                self.storage.insert_excluded_interval(
                    start_time=self._active_start,
                    end_time=final_end,
                    duration_seconds=duration,
                    reason="excluded_app",
                )
            else:
                self.storage.insert_app_session(
                    app_name=self._active_app,
                    window_title_hash=self._active_title_hash,
                    window_title_ext=self._active_title_ext,
                    start_time=self._active_start,
                    end_time=final_end,
                    duration_seconds=duration,
                    is_past=0,
                    source="live",
                )
        self._active_start = None
        self._active_end = None
        self._active_app = None

    def flush(self) -> None:
        """Flushes any currently open session to storage."""
        if (
            self._active_app is not None
            and self._active_start is not None
            and self._active_end is not None
        ):
            if self._active_end > self._active_start:
                self._commit_active_session(end_time=self._active_end)
            else:
                self._active_start = None
                self._active_end = None
                self._active_app = None

        if self._pending_copy is not None:
            self._complete_clipboard_transfer(target_app="", paste_time=None)

    def delete(self, target: TimeRange | str) -> None:
        """Deletes records within the specified time range or scope string.

        Supported scopes: 'today', 'last_7_days', 'last_30_days', 'all'.
        """
        self.flush()

        if isinstance(target, str):
            scope = target.lower().strip()
            now = self.clock()
            if scope == "all":
                self.storage.delete_range(None, None)
            elif scope == "today":
                today_start = datetime(
                    now.year, now.month, now.day, tzinfo=now.tzinfo or timezone.utc
                )
                self.storage.delete_range(today_start, None)
            elif scope == "last_7_days":
                start = now - timedelta(days=7)
                self.storage.delete_range(start, None)
            elif scope == "last_30_days":
                start = now - timedelta(days=30)
                self.storage.delete_range(start, None)
            else:
                raise ValueError(f"Unknown deletion scope: {target}")
        elif isinstance(target, TimeRange):
            self.storage.delete_range(target.start, target.end)
        else:
            raise TypeError(f"Expected TimeRange or str, got {type(target)}")

    def export(
        self,
        time_range: TimeRange,
        password: str,
        destination: str | Path,
    ) -> Path:
        """Exports diagnostic archive encrypted with AES-256."""
        self.flush()

        dest_path = Path(destination)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db_path = Path(tmpdir) / "data.sqlite"
            redaction_report = self.storage.export_subset(
                temp_db_path,
                start=time_range.start,
                end=time_range.end,
                excluded_apps=self._excluded_apps,
            )

            session_count = self.storage.count_sessions(start=time_range.start, end=time_range.end)
            machine_id = self.key_manager.get_machine_id()

            manifest: dict[str, Any] = {
                "version": MANIFEST_VERSION,
                "exported_at": self.clock().isoformat(),
                "time_range": {
                    "start": time_range.start.isoformat(),
                    "end": time_range.end.isoformat(),
                },
                "machine_id": machine_id,
                "counts": {
                    "app_sessions": session_count,
                },
            }
            manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
            redaction_report_json = json.dumps(redaction_report, indent=2, ensure_ascii=False)
            summary_data = generate_summary(temp_db_path)
            summary_json = json.dumps(summary_data, indent=2, ensure_ascii=False)

            readme_text = (
                "FlowLens Diagnostic Export\n"
                "==========================\n\n"
                "This archive contains diagnostic activity data exported by FlowLens Collector.\n\n"
                "Included files:\n"
                "- data.sqlite: SQLite database of collected session/event tables.\n"
                "- manifest.json: Export metadata, time range, machine ID, and session counts.\n"
                "- summary.json: Pre-aggregated statistics (live/past durations and transfers).\n"
                "- redaction_report.json: Audit of excluded records filtered out.\n"
                "- README.txt: This summary document.\n\n"
                "How to Open:\n"
                "Open with 7-Zip using the AES-256 password specified during export.\n\n"
                "Data Granularity (Live vs Past):\n"
                "- Live records (is_past = 0): High-resolution focus, typing, and transfers.\n"
                "- Past records (is_past = 1): Coarse footprints from Windows records.\n\n"
                "Privacy & Analysis:\n"
                "- Window titles and file names are keyed HMAC-SHA256 hashes.\n"
                "- Raw text, keystroke characters, and clipboard contents are never stored.\n"
                "- Refer to docs/consultant-guide.md for Claude Code analysis workflows.\n"
            )

            # Build AES-256 ZIP using pyzipper
            with pyzipper.AESZipFile(
                dest_path,
                "w",
                compression=pyzipper.ZIP_DEFLATED,
                encryption=pyzipper.WZ_AES,
            ) as zf:
                zf.setpassword(password.encode("utf-8"))
                zf.write(temp_db_path, arcname="data.sqlite")
                zf.writestr("manifest.json", manifest_json)
                zf.writestr("redaction_report.json", redaction_report_json)
                zf.writestr("summary.json", summary_json)
                zf.writestr("README.txt", readme_text)

        return dest_path

    def get_status(self) -> dict[str, Any]:
        """Returns the current operational status and recording statistics."""
        self.flush()
        stats = self.storage.get_stats()
        db_size = 0
        if self.db_path.exists():
            db_size += self.db_path.stat().st_size
        wal_path = Path(str(self.db_path) + "-wal")
        if wal_path.exists():
            db_size += wal_path.stat().st_size

        return {
            "is_recording": not self._is_paused,
            "is_paused": self._is_paused,
            "earliest_session": stats["earliest_session"],
            "total_duration_seconds": stats["total_duration_seconds"],
            "session_count": stats["session_count"],
            "database_size_bytes": db_size,
        }
