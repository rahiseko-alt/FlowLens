"""The resident Collector: consent, Past Import, then Live Capture from the tray.

Threads:
- main thread: the hidden window (tray, lock/sleep messages) and every Tk screen;
- "hooks": the keyboard and mouse hooks and nothing else, so a busy screen never
  delays keyboard input or gets the hooks removed by Windows;
- "activity": foreground window and idle polling;
- "input": turns hook events, clipboard changes and focus changes into observations.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
from pathlib import Path

import win32gui

from flowlens.core import Recorder
from flowlens.core.app_state import AlreadyRunningError, SingleInstanceLock
from flowlens.core.config import ConfigManager
from flowlens.core.consent import ConsentManager
from flowlens.core.logging_config import close_logging, setup_logging
from flowlens.windows import autostart
from flowlens.windows.consent_dialog import ConsentDialog, run_past_import_with_progress
from flowlens.windows.input_watcher import InputHooks, InputWorker
from flowlens.windows.past_import import windows_past_providers
from flowlens.windows.settings_window import SettingsWindow
from flowlens.windows.shell import WINDOW_CLASS, WM_OPEN_SETTINGS, TrayShell
from flowlens.windows.status_window import StatusWindow
from flowlens.windows.watcher import ActivityWatcher


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "FlowLens"


class CollectorApp:
    def __init__(self, storage_dir: Path | None = None):
        # Only cheap, file-free setup here: a second copy (e.g. the watchdog) must not
        # open the database, the log or touch temp files before it holds the lock.
        self.storage_dir = storage_dir or data_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.lock = SingleInstanceLock(self.storage_dir)
        self.consent = ConsentManager(self.storage_dir)
        self.events: queue.Queue = queue.Queue(maxsize=10_000)

    def _build(self) -> None:
        self.log = setup_logging(self.storage_dir / "logs" / "collector.log")
        self.recorder = Recorder(self.storage_dir)
        self.recorder.remove_leftover_temp_files()
        self.activity = ActivityWatcher(self.recorder)
        self.input = InputWorker(self.recorder, self.events)
        self.hooks = InputHooks(self.events)
        self.tray = TrayShell(
            self.recorder,
            on_status=self.show_status,
            on_settings=self.show_settings,
            on_exit=self.exit_by_user,
        )

    def run(self, watchdog: bool = False, smoke_seconds: float = 0) -> int:
        """`watchdog`: started by the scheduled task that restarts FlowLens after a crash.

        It does nothing if FlowLens is running, if the employee has not consented, or
        if the employee chose 終了 (until the next login).
        """
        if watchdog and (
            not self.consent.has_consent() or ConfigManager(self.storage_dir).get("user_exited")
        ):
            return 0
        try:
            self.lock.acquire()
        except AlreadyRunningError:
            if not watchdog:
                open_settings_in_running_instance()  # e.g. clicked in the Start menu again
            return 0
        self._build()
        if not watchdog:
            self.recorder.user_exited = False  # a login or a manual start clears it
        try:
            self.log.info("collector started")
            if smoke_seconds:
                self.consent.grant_consent()  # automated check only: no screens
            elif not self.consent.has_consent():
                if not self._first_run():
                    self.log.info("consent declined")
                    return 0
                first_run = True
            else:
                first_run = False
            self.activity.start()
            self.input.start()
            self.tray.create()
            try:
                self.hooks.start()
            except OSError as exc:  # keep recording windows and clipboard without them
                self.log.error("input hooks unavailable: %s", type(exc).__name__)
            self.log.info("live capture started")
            if smoke_seconds:
                threading.Timer(smoke_seconds, self.tray.close).start()
            elif first_run:
                self.tray.notify(
                    "FlowLens は記録を始めました",
                    "画面右下のこのアイコンから、一時停止・設定・診断データの書き出しができます。",
                )
            self.tray.run()
            return 0
        except Exception as exc:
            log_crash(self.log, exc)
            return 1
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
        self.consent.grant_consent()
        self.recorder.set_enabled_past_sources(dialog.selected_sources)
        if getattr(sys, "frozen", False):
            autostart.set_autostart("FlowLens", f'"{sys.executable}"')
        report = run_past_import_with_progress(
            self.recorder, windows_past_providers(self.storage_dir)
        )
        self.log.info(
            "past import: %s", {name: result["status"] for name, result in report.items()}
        )
        return True

    def read_more_sources(self, sources: list[str]) -> dict:
        enabled = set(self.recorder.get_enabled_past_sources() or []) | set(sources)
        self.recorder.set_enabled_past_sources(sorted(enabled))
        providers = {
            k: v for k, v in windows_past_providers(self.storage_dir).items() if k in sources
        }
        return run_past_import_with_progress(self.recorder, providers)

    def show_status(self) -> None:
        StatusWindow(
            self.recorder, self.consent.get_consent_timestamp(), on_toggle=self.tray.refresh
        ).show()

    def show_settings(self) -> None:
        SettingsWindow(self.recorder, self.read_more_sources).show()

    def exit_by_user(self) -> None:
        """終了 from the tray: stay stopped until the next login, even for the watchdog."""
        self.recorder.user_exited = True
        self.stop()

    def stop(self) -> None:
        self.hooks.stop()
        self.activity.stop()
        self.input.stop()
        self.recorder.flush()


def self_check() -> int:
    """`flowlens.exe --self-check`: used by the build to prove the packaged app starts.

    Loads every part and records into a throw-away folder, without showing any window.
    """
    import tempfile
    from datetime import datetime, timezone

    import uiautomation  # noqa: F401  (packaging: DLLs present)

    from flowlens.core import WindowObservation

    with tempfile.TemporaryDirectory() as tmp:
        recorder = Recorder(Path(tmp))
        recorder.observe(WindowObservation(datetime.now(timezone.utc), "flowlens.exe"))
        recorder.flush()
        recorder.storage.close()
    return 0


def log_crash(log, exc: BaseException) -> None:
    """Where it failed, without the message (a message could carry a title or a path)."""
    frames = traceback.extract_tb(exc.__traceback__)
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in reversed(frames))
    log.error("crashed: %s at %s", type(exc).__name__, where)


def open_settings_in_running_instance() -> None:
    hwnd = win32gui.FindWindow(WINDOW_CLASS, None)
    if hwnd:
        win32gui.PostMessage(hwnd, WM_OPEN_SETTINGS, 0, 0)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--self-check" in args:
        return self_check()
    if "--smoke" in args:
        # Automated check on a build machine: the whole app for a few seconds, no screens.
        data = Path(args[args.index("--smoke") + 1])
        return CollectorApp(data).run(smoke_seconds=8)
    return CollectorApp().run(watchdog="--watchdog" in args)
