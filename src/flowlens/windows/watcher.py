# Based on DeskMate (https://github.com/zhaohb/deskmate)
# Original files: a11y/win_events.py, a11y/activity_feed.py
#
# MIT License
# Copyright (c) 2024-2026 zhaohb
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Windows activity observation entry point for FlowLens.

Observes foreground window transitions, user idle states, system lock/unlock,
sleep/resume, and session disconnects, passing raw observations directly to
FlowLens Core Recorder without inspection, retention, or local storage.
"""

import threading
import time
from datetime import datetime, timezone

import psutil
import win32api
import win32gui
import win32process

from flowlens.core.models import (
    IdleObservation,
    LockObservation,
    SessionDisconnectObservation,
    SleepObservation,
    WindowObservation,
)
from flowlens.core.recorder import Recorder


class WindowsActivityWatcher:
    """Thin Windows watcher for window focus, idle detection, and session state.

    Collects active foreground application name, window title, and user activity,
    and forwards observations to FlowLens Recorder. Does not retain or persist
    window titles or user content.
    """

    def __init__(
        self,
        recorder: Recorder,
        poll_interval: float = 1.0,
        idle_threshold_seconds: float = 300.0,
    ) -> None:
        self.recorder = recorder
        self.poll_interval = poll_interval
        self.idle_threshold_seconds = idle_threshold_seconds

        self._running = False
        self._thread: threading.Thread | None = None
        self._is_idle = False
        self._last_app = ""
        self._last_title = ""

    def get_foreground_window_info(self) -> tuple[str, str]:
        """Queries the current foreground window process name and window title."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "", ""

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid <= 0:
                return "", ""
            proc = psutil.Process(pid)
            app_name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            app_name = "Unknown"

        try:
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            title = ""

        return app_name, title

    def get_idle_seconds(self) -> float:
        """Returns the number of seconds since the last user input."""
        try:
            last_input = win32api.GetLastInputInfo()
            tick_count = win32api.GetTickCount()
            # Handle 32-bit tick wrap-around if necessary
            elapsed_ms = max(0, tick_count - last_input)
            return elapsed_ms / 1000.0
        except Exception:
            return 0.0

    def poll_once(self, now: datetime | None = None) -> None:
        """Performs a single observation cycle for window focus and idle state."""
        current_time = now or datetime.now(timezone.utc)

        # 1. Idle detection
        idle_seconds = self.get_idle_seconds()
        if idle_seconds >= self.idle_threshold_seconds:
            if not self._is_idle:
                self._is_idle = True
                self.recorder.observe(IdleObservation(timestamp=current_time, is_idle=True))
        else:
            if self._is_idle:
                self._is_idle = False
                self.recorder.observe(IdleObservation(timestamp=current_time, is_idle=False))

        # 2. Foreground window detection (only if not idle)
        if not self._is_idle:
            app_name, title = self.get_foreground_window_info()
            if app_name:
                self.recorder.observe(
                    WindowObservation(
                        timestamp=current_time,
                        app_name=app_name,
                        window_title=title,
                    )
                )

    def handle_session_change(self, event_type: str, now: datetime | None = None) -> None:
        """Handles Windows session changes (lock, unlock, disconnect, connect)."""
        current_time = now or datetime.now(timezone.utc)
        ev = event_type.lower()
        if ev in ("lock", "session_lock"):
            self.recorder.observe(LockObservation(timestamp=current_time, is_locked=True))
        elif ev in ("unlock", "session_unlock"):
            self.recorder.observe(LockObservation(timestamp=current_time, is_locked=False))
        elif ev in ("disconnect", "session_disconnect"):
            self.recorder.observe(
                SessionDisconnectObservation(timestamp=current_time, is_disconnected=True)
            )
        elif ev in ("connect", "session_connect"):
            self.recorder.observe(
                SessionDisconnectObservation(timestamp=current_time, is_disconnected=False)
            )

    def handle_power_event(self, event_type: str, now: datetime | None = None) -> None:
        """Handles Windows power management events (sleep, resume)."""
        current_time = now or datetime.now(timezone.utc)
        ev = event_type.lower()
        if ev in ("sleep", "suspend"):
            self.recorder.observe(SleepObservation(timestamp=current_time, is_asleep=True))
        elif ev in ("resume", "resume_automatic"):
            self.recorder.observe(SleepObservation(timestamp=current_time, is_asleep=False))

    def _loop(self) -> None:
        while self._running:
            try:
                self.poll_once()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def start(self) -> None:
        """Starts background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops background monitoring loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
