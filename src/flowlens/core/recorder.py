import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pyzipper

from flowlens.core.crypto import KeyManager
from flowlens.core.models import Observation, TimeRange, WindowObservation
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

    @property
    def is_paused(self) -> bool:
        return self._is_paused

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

        if isinstance(observation, WindowObservation):
            self._handle_window_observation(observation)

    def _handle_window_observation(self, obs: WindowObservation) -> None:
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

        # Check if switched app
        if app_name != self._active_app:
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
            # Same app
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
