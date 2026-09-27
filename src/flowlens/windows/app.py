"""The resident Collector: consent, Past Import, then Live Capture from the tray.

Threads:
- main thread: the hidden window (tray, lock/sleep messages), the keyboard and
  mouse hooks, and every Tk screen;
- "activity": foreground window and idle polling;
- "input": turns hook events, clipboard changes and focus changes into observations.
"""

from __future__ import annotations

import os
import queue
import sys
from pathlib import Path

from flowlens.core import Recorder
from flowlens.core.app_state import AlreadyRunningError, SingleInstanceLock
from flowlens.core.consent import ConsentManager
from flowlens.core.logging_config import close_logging, setup_logging
from flowlens.windows import autostart
from flowlens.windows.consent_dialog import ConsentDialog, run_past_import_with_progress
from flowlens.windows.input_watcher import InputHooks, InputWorker
from flowlens.windows.past_import import windows_past_providers
from flowlens.windows.settings_window import SettingsWindow
from flowlens.windows.shell import TrayShell
from flowlens.windows.status_window import StatusWindow
from flowlens.windows.watcher import ActivityWatcher


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "FlowLens"


class CollectorApp:
    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or data_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.log = setup_logging(self.storage_dir / "logs" / "collector.log")
        self.lock = SingleInstanceLock(self.storage_dir)
        self.consent = ConsentManager(self.storage_dir)
        self.recorder = Recorder(self.storage_dir)
        self.events: queue.Queue = queue.Queue(maxsize=10_000)
        self.activity = ActivityWatcher(self.recorder)
        self.input = InputWorker(self.recorder, self.events)
        self.hooks = InputHooks(self.events)
        self.tray = TrayShell(
            self.recorder,
            on_status=self.show_status,
            on_settings=self.show_settings,
            on_exit=self.stop,
        )

    def run(self) -> int:
        try:
            self.lock.acquire()
        except AlreadyRunningError:
            self.log.info("already running")
            return 0
        try:
            self.log.info("collector started")
            if not self.consent.has_consent() and not self._first_run():
                self.log.info("consent declined")
                return 0
            self.activity.start()
            self.input.start()
            self.tray.create()
            self.hooks.install()
            self.log.info("live capture started")
            self.tray.run()
            return 0
        finally:
            self.stop()
            self.tray.destroy()
            self.lock.release()
            self.log.info("collector stopped")
            close_logging()

    def _first_run(self) -> bool:
        dialog = ConsentDialog()
        if not dialog.show():
            return False
        self.consent.grant_consent(dialog.selected_sources)
        self.recorder.set_enabled_past_sources(dialog.selected_sources)
        if getattr(sys, "frozen", False):
            autostart.set_autostart("FlowLens", f'"{sys.executable}"')
        report = run_past_import_with_progress(self.recorder, windows_past_providers())
        self.log.info(
            "past import: %s", {name: result["status"] for name, result in report.items()}
        )
        return True

    def read_more_sources(self, sources: list[str]) -> dict:
        enabled = set(self.recorder.get_enabled_past_sources() or []) | set(sources)
        self.recorder.set_enabled_past_sources(sorted(enabled))
        self.consent.grant_consent(sorted(enabled))
        providers = {k: v for k, v in windows_past_providers().items() if k in sources}
        return run_past_import_with_progress(self.recorder, providers)

    def show_status(self) -> None:
        StatusWindow(
            self.recorder, self.consent.get_consent_timestamp(), on_toggle=self.tray.refresh
        ).show()

    def show_settings(self) -> None:
        SettingsWindow(self.recorder, self.read_more_sources).show()

    def stop(self) -> None:
        self.hooks.uninstall()
        self.activity.stop()
        self.input.stop()
        self.recorder.flush()


def main() -> int:
    return CollectorApp().run()
