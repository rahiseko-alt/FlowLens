from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flowlens.core.app_state import AlreadyRunningError, SingleInstanceLock
from flowlens.core.consent import ConsentManager
from flowlens.core.logging_config import setup_logging
from flowlens.core.recorder import Recorder
from flowlens.windows.consent_dialog import ConsentDialog, show_import_results_dialog
from flowlens.windows.input_watcher import WindowsInputWatcher
from flowlens.windows.past_import import run_windows_past_import
from flowlens.windows.status_window import StatusWindow
from flowlens.windows.watcher import WindowsActivityWatcher


class CollectorApp:
    """The resident FlowLens Windows Collector application coordinator."""

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        clock: Callable[[], Any] | None = None,
    ):
        if storage_dir is None:
            appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "."
            storage_dir = Path(appdata) / "FlowLens"

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.logger = setup_logging(self.storage_dir / "flowlens.log")
        self.lock = SingleInstanceLock(self.storage_dir)
        self.consent_manager = ConsentManager(self.storage_dir)
        self.recorder = Recorder(storage_dir=self.storage_dir, clock=clock)

        self.activity_watcher: WindowsActivityWatcher | None = None
        self.input_watcher: WindowsInputWatcher | None = None
        self.is_running = False

    def start(self, interactive_ui: bool = True) -> bool:
        """Starts the application. Returns True if started successfully, False if aborted."""
        try:
            self.lock.acquire()
        except AlreadyRunningError:
            self.logger.warning("Another instance of FlowLens is already running. Exiting.")
            return False

        self.logger.info("FlowLens Collector starting up.")

        # Check consent
        if not self.consent_manager.has_consent():
            if not interactive_ui:
                self.logger.info("Non-interactive mode and no consent granted. Exiting.")
                self.lock.release()
                return False

            dialog = ConsentDialog()
            consented = dialog.show()
            if not consented:
                self.logger.info("User declined consent. Exiting without recording.")
                self.lock.release()
                return False

            # Save consent
            selected_sources = dialog.selected_sources
            self.consent_manager.grant_consent(selected_sources)
            self.logger.info("Consent granted with %d sources selected.", len(selected_sources))

            # Apply past sources selection to recorder
            self.recorder.set_enabled_past_sources(selected_sources)

            # Perform Past Import
            self.logger.info("Executing initial Past Import.")
            report = run_windows_past_import(self.recorder, max_days=30)
            counts = {k: v["count"] for k, v in report.items()}
            self.logger.info("Past Import completed: %s", counts)

            if interactive_ui:
                show_import_results_dialog(report)
        else:
            enabled_sources = self.consent_manager.get_enabled_sources()
            self.recorder.set_enabled_past_sources(enabled_sources)
            self.logger.info(
                "Existing consent loaded with %d enabled sources.", len(enabled_sources)
            )

        # Start live capture watchers
        self._start_watchers()
        self.is_running = True
        self.logger.info("Live capture watchers started.")
        return True

    def _start_watchers(self) -> None:
        self.activity_watcher = WindowsActivityWatcher(
            recorder=self.recorder,
            poll_interval=1.0,
            idle_threshold=300.0,
        )
        self.activity_watcher.start()

        self.input_watcher = WindowsInputWatcher(
            recorder=self.recorder,
            flush_interval=5.0,
        )
        self.input_watcher.start()

    def pause(self) -> None:
        """Pauses live recording."""
        self.recorder.pause()
        self.logger.info("Collector paused by user.")

    def resume(self) -> None:
        """Resumes live recording."""
        self.recorder.resume()
        self.logger.info("Collector resumed by user.")

    def show_status(self) -> None:
        """Displays the status window."""
        win = StatusWindow(self.recorder, on_toggle_pause=None)
        win.show()

    def stop(self) -> None:
        """Stops all watchers and releases lock."""
        self.logger.info("Collector shutting down.")
        if self.activity_watcher:
            self.activity_watcher.stop()
            self.activity_watcher = None

        if self.input_watcher:
            self.input_watcher.stop()
            self.input_watcher = None

        self.recorder.flush()
        self.lock.release()
        self.is_running = False
        self.logger.info("Collector shutdown completed.")
