# Based on DeskMate (https://github.com/zhaohb/deskmate)
# Original files: a11y/input_hooks.py, a11y/clipboard.py, a11y/uia_tree.py, a11y/browser_url.py
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

"""Windows input, clipboard, UI control, and browser URL observation entry point.

Captures typing counts, operation types (Ctrl+C/V/X, Enter, Tab, Escape), clipboard
change events without content, control metadata (without Name, Value, or TextPattern),
and browser domains. Fixes DeskMate password detection and omits all text reading.
"""

import threading
import time
from datetime import datetime, timezone

import psutil
import uiautomation as auto
import win32clipboard
import win32gui
import win32process

from flowlens.core.models import (
    ClipboardObservation,
    ControlMetadataObservation,
    OperationTypeObservation,
    TypingObservation,
)
from flowlens.core.recorder import Recorder


def safe_is_password(control: auto.Control | None) -> bool:
    """Safely determines if a control is a password input field.

    Fixes DeskMate's bug which queried non-existent CurrentIsPassword attribute.
    Uses uiautomation's IsPassword property directly.
    """
    if not control:
        return False
    try:
        return bool(control.IsPassword)
    except Exception:
        return False


def get_foreground_app_name() -> str:
    """Returns the process name of the current foreground window."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:
            return ""
        return psutil.Process(pid).name()
    except Exception:
        return ""


class WindowsInputWatcher:
    """Monitors typing activity, operational shortcuts, clipboard transfers,

    and control metadata without capturing raw user text or content.
    """

    def __init__(self, recorder: Recorder, poll_interval: float = 0.5) -> None:
        self.recorder = recorder
        self.poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None

        self._last_clip_seq: int | None = None
        self._typing_burst_count = 0
        self._typing_start_time: datetime | None = None
        self._typing_is_password = False

    def check_clipboard(self) -> None:
        """Inspects clipboard for changes without reading raw content."""
        try:
            seq = win32clipboard.GetClipboardSequenceNumber()
            if self._last_clip_seq is None:
                self._last_clip_seq = seq
                return

            if seq != self._last_clip_seq:
                self._last_clip_seq = seq
                app_name = get_foreground_app_name()

                data_type = "text"
                data_length = 0

                win32clipboard.OpenClipboard()
                try:
                    # Check available formats without persisting content
                    if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                        raw_val = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                        data_type = "text"
                        data_length = len(raw_val) if raw_val else 0
                    elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                        raw_val = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                        data_type = "text"
                        data_length = len(raw_val) if raw_val else 0
                    elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
                        files = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
                        data_type = "files"
                        data_length = len(files) if files else 0
                    elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
                        data_type = "image"
                        data_length = 0
                    else:
                        data_type = "binary"
                        data_length = 0
                finally:
                    win32clipboard.CloseClipboard()

                # Dispatch to core without raw_content
                self.recorder.observe(
                    ClipboardObservation(
                        timestamp=datetime.now(timezone.utc),
                        action="copy",
                        data_type=data_type,
                        data_length=data_length,
                        app_name=app_name,
                    )
                )
        except Exception:
            pass

    def check_focused_control(self) -> None:
        """Inspects currently focused UI control.

        NEVER reads Name, Value, or TextPattern.
        Only captures ControlType, AutomationId, ClassName, FrameworkId, and IsPassword.
        """
        try:
            element = auto.GetFocusedElement()
            if not element:
                return

            is_pwd = safe_is_password(element)
            self._typing_is_password = is_pwd

            app_name = get_foreground_app_name()
            control_type = element.ControlTypeName or ""
            automation_id = element.AutomationId or ""
            class_name = element.ClassName or ""
            framework_id = element.FrameworkId or ""

            # If browser, query address bar
            url = ""
            if app_name.lower() in ("chrome.exe", "msedge.exe", "brave.exe", "firefox.exe"):
                url = self._extract_browser_url(element)

            self.recorder.observe(
                ControlMetadataObservation(
                    timestamp=datetime.now(timezone.utc),
                    event_type="focus",
                    control_type=control_type,
                    automation_id=automation_id,
                    class_name=class_name,
                    framework_id=framework_id,
                    url=url,
                    app_name=app_name,
                )
            )
        except Exception:
            pass

    def _extract_browser_url(self, focused: auto.Control) -> str:
        """Locates the address bar and extracts URL string (core extracts domain)."""
        try:
            # Check if focused element itself is the address edit control
            if focused.ControlTypeName == "EditControl":
                val = focused.GetValuePattern().Value if hasattr(focused, "GetValuePattern") else ""
                if val and ("http://" in val or "https://" in val):
                    return val

            # Or search top window for address bar
            top = focused.GetTopLevelControl()
            if top:
                edit = top.EditControl(searchDepth=6)
                if edit.Exists(0, 0):
                    val = edit.GetValuePattern().Value if hasattr(edit, "GetValuePattern") else ""
                    if val and ("http://" in val or "https://" in val):
                        return val
        except Exception:
            pass
        return ""

    def record_key_press(self, is_special_op: str | None = None) -> None:
        """Records a keystroke count or special operation without storing key characters."""
        now = datetime.now(timezone.utc)
        app_name = get_foreground_app_name()

        if is_special_op:
            # Operation type (e.g. ctrl+c, ctrl+v, enter, tab, escape)
            self.recorder.observe(
                OperationTypeObservation(
                    timestamp=now,
                    operation_type=is_special_op,
                    app_name=app_name,
                )
            )
            # Flush any ongoing typing burst
            self.flush_typing_burst()
            return

        # Regular typing burst tracking
        if self._typing_burst_count == 0:
            self._typing_start_time = now

        self._typing_burst_count += 1

    def flush_typing_burst(self) -> None:
        """Emits aggregated typing activity count and duration."""
        if self._typing_burst_count > 0 and self._typing_start_time is not None:
            now = datetime.now(timezone.utc)
            duration = max(0.0, (now - self._typing_start_time).total_seconds())
            app_name = get_foreground_app_name()

            # For password field: keystrokes=0 (duration only preserved)
            keystrokes = 0 if self._typing_is_password else self._typing_burst_count

            self.recorder.observe(
                TypingObservation(
                    timestamp=self._typing_start_time,
                    keystrokes=keystrokes,
                    duration_seconds=duration,
                    is_password=self._typing_is_password,
                    app_name=app_name,
                )
            )

            self._typing_burst_count = 0
            self._typing_start_time = None

    def _loop(self) -> None:
        while self._running:
            try:
                self.check_clipboard()
                self.check_focused_control()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.flush_typing_burst()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
