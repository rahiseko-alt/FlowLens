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

"""Foreground window and idle watcher.

Polls once a second and hands the foreground app and its title to the Recorder,
which hashes the title before anything is stored. Idle is reported as starting at
the last input, so the waiting time before it is noticed is not counted as work.
Lock, sleep and disconnect arrive as window messages (see shell.py).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

import psutil
import win32api
import win32gui
import win32process

from flowlens.core import IdleObservation, Recorder, WindowObservation

log = logging.getLogger("flowlens")


def foreground_app() -> tuple[str, str]:
    """(process name, window title) of the foreground window, or ("", "")."""
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return "", ""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        name = psutil.Process(pid).name() if pid > 0 else ""
    except (psutil.Error, OSError):
        name = ""
    try:
        title = win32gui.GetWindowText(hwnd) or ""
    except win32gui.error:
        title = ""
    return name, title


def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input (tick counter wraps at 2^32 ms)."""
    elapsed = (win32api.GetTickCount() - win32api.GetLastInputInfo()) & 0xFFFFFFFF
    return elapsed / 1000.0


class ActivityWatcher:
    def __init__(self, recorder: Recorder, poll_interval: float = 1.0):
        self.recorder = recorder
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._idle = False

    def poll_once(self) -> None:
        now = datetime.now(timezone.utc)
        idle = idle_seconds()
        if idle >= self.recorder.idle_threshold_seconds:
            if not self._idle:
                self._idle = True
                last_input = now - timedelta(seconds=idle)
                self.recorder.observe(IdleObservation(timestamp=last_input, is_idle=True))
            return
        if self._idle:
            self._idle = False
            self.recorder.observe(IdleObservation(timestamp=now, is_idle=False))
        app, title = foreground_app()
        if app:
            self.recorder.observe(
                WindowObservation(timestamp=now, app_name=app, window_title=title)
            )

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # only the type: messages could carry titles
                log.error("activity watcher cycle failed: %s", type(exc).__name__)
            self._stop.wait(self.poll_interval)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="activity", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
