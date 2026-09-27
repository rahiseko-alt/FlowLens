import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pyzipper

from flowlens.core.crypto import KeyManager
from flowlens.core.models import (
    IdleObservation,
    LockObservation,
    Observation,
    OperationTypeObservation,
    SessionDisconnectObservation,
    SleepObservation,
    TimeRange,
    TypingObservation,
    WindowObservation,
)
from flowlens.core.storage import Storage

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
        self.clock = clock or (lambda: datetime.now(timezone.utc))

        self._active_app: str | None = None
        self._active_title_hash: str = ""
        self._active_title_ext: str = ""
        self._active_start: datetime | None = None
        self._active_end: datetime | None = None

        self._is_paused = False
        self._excluded_apps: set[str] = set()
        self._retention_days: int = 30
        self._idle_threshold_seconds: float = 300.0

        self._is_idle = False
        self._is_locked = False
        self._is_asleep = False
        self._is_disconnected = False

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

    def pause(self) -> None:
        self.flush()
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    def set_excluded_apps(self, apps: list[str]) -> None:
        self._excluded_apps = {app.lower().strip() for app in apps}

    def set_retention_days(self, days: int) -> None:
        self._retention_days = days

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
        elif isinstance(observation, WindowObservation):
            self._handle_window_observation(observation)

    def _handle_typing_observation(self, obs: TypingObservation) -> None:
        if self.is_away:
            return

        app_name = obs.app_name or self._active_app or "Unknown"
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

        app_name = obs.app_name or self._active_app or "Unknown"
        self.storage.insert_operation_type(
            app_name=app_name,
            operation_type=obs.operation_type.lower(),
            timestamp=obs.timestamp,
            is_past=0,
            source="live",
        )

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

    def delete(self, time_range: TimeRange) -> None:
        """Deletes records within the specified time range."""
        self.flush()
        # Will be extended for full deletion features in #13
        query = "DELETE FROM app_sessions WHERE start_time >= ? AND end_time <= ?"
        conn = self.storage._connect()
        try:
            conn.execute(query, (time_range.start.isoformat(), time_range.end.isoformat()))
            conn.commit()
        finally:
            conn.close()

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
            self.storage.export_subset(temp_db_path, start=time_range.start, end=time_range.end)

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

        return dest_path
