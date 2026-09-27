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

"""Keyboard, mouse, clipboard and UI-element observation without content (ADR 0002).

- Keyboard: a low-level hook classifies each key press into a kind (a plain key,
  ctrl+c/x/v, enter, tab, escape, shortcut). The key itself is never kept.
- Mouse: only the fact of a left click; the point is used once to find the UI
  element under it and then dropped.
- Clipboard: the kind of data and its size, read from the memory block size.
  The text or file names are never read.
- UI elements: ControlType, AutomationId, ClassName, FrameworkId, toggle state and
  whether it is a password box. Name, Value and TextPattern are not read.
- Browser: the one exception to "no Value": the address bar of Chrome/Edge is read
  once per page change, only while it is not being typed into, and cut down to its
  host name on the spot (ADR 0002 permits the domain).
"""

from __future__ import annotations

import ctypes
import logging
import queue
import threading
from ctypes import wintypes
from datetime import datetime, timedelta, timezone

import psutil
import uiautomation as auto
import win32gui

from flowlens.core import (
    ClipboardObservation,
    ControlMetadataObservation,
    OperationTypeObservation,
    Recorder,
    TypingObservation,
    sanitize,
)
from flowlens.windows.watcher import foreground_app

log = logging.getLogger("flowlens")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_QUIT = 0x0012
WM_KEYDOWN, WM_SYSKEYDOWN, WM_LBUTTONDOWN = 0x0100, 0x0104, 0x0201
VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x11, 0x12, 0x5B, 0x5C
MODIFIER_KEYS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, VK_LWIN, VK_RWIN, 0x14}
PLAIN_OPS = {0x0D: "enter", 0x09: "tab", 0x1B: "escape"}
CTRL_OPS = {0x43: "ctrl+c", 0x58: "ctrl+x", 0x56: "ctrl+v"}
CF_BITMAP, CF_DIB, CF_UNICODETEXT, CF_HDROP = 2, 8, 13, 15
BROWSERS = {"chrome.exe", "msedge.exe"}
OMNIBOX_CLASS = "OmniboxViewViews"
TYPING_PAUSE = timedelta(seconds=2)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT


def _down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def classify_key(vk: int, is_sys: bool) -> str | None:
    """The kind of a key press, never the key: None for modifiers alone."""
    if vk in MODIFIER_KEYS:
        return None
    ctrl = _down(VK_CONTROL)
    if ctrl and vk in CTRL_OPS:
        return CTRL_OPS[vk]
    if ctrl or is_sys or _down(VK_MENU) or _down(VK_LWIN) or _down(VK_RWIN):
        return "shortcut"
    return PLAIN_OPS.get(vk, "key")


class InputHooks:
    """Low-level keyboard and mouse hooks on their own thread and message loop.

    Windows removes low-level hooks whose thread does not answer quickly, so the hooks
    get a thread that does nothing else: the callbacks classify, note the foreground
    window, enqueue, and return. All other work happens on InputWorker's thread.
    """

    def __init__(self, events: queue.Queue):
        self.events = events
        self._keyboard_proc = HOOKPROC(self._on_key)
        self._mouse_proc = HOOKPROC(self._on_mouse)
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: Exception | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="hooks", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        if self._error:
            raise self._error

    def stop(self) -> None:
        if self._thread is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        module = kernel32.GetModuleHandleW(None)
        hooks = []
        try:
            for kind, proc in (
                (WH_KEYBOARD_LL, self._keyboard_proc),
                (WH_MOUSE_LL, self._mouse_proc),
            ):
                hook = user32.SetWindowsHookExW(kind, proc, module, 0)
                if not hook:
                    raise ctypes.WinError(ctypes.get_last_error())
                hooks.append(hook)
        except Exception as exc:
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hook in hooks:
                user32.UnhookWindowsHookEx(hook)

    def _on_key(self, code: int, wparam: int, lparam: int) -> int:
        if code == 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            try:
                vk = KBDLLHOOKSTRUCT.from_address(lparam).vkCode
                kind = classify_key(vk, wparam == WM_SYSKEYDOWN)
                if kind:
                    event = (kind, datetime.now(timezone.utc), user32.GetForegroundWindow())
                    self.events.put_nowait(event)
            except Exception:
                pass  # a hook must never fail
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_mouse(self, code: int, wparam: int, lparam: int) -> int:
        if code == 0 and wparam == WM_LBUTTONDOWN:
            try:
                pt = MSLLHOOKSTRUCT.from_address(lparam).pt
                event = (
                    "click",
                    datetime.now(timezone.utc),
                    user32.GetForegroundWindow(),
                    pt.x,
                    pt.y,
                )
                self.events.put_nowait(event)
            except Exception:
                pass
        return user32.CallNextHookEx(None, code, wparam, lparam)


def clipboard_shape() -> tuple[str, int]:
    """(data type, size) of the clipboard, from memory block sizes only."""
    if not user32.OpenClipboard(None):
        return "other", 0
    try:
        if user32.IsClipboardFormatAvailable(CF_HDROP):
            handle = user32.GetClipboardData(CF_HDROP)
            return "files", int(
                shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
            ) if handle else 0
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            size = kernel32.GlobalSize(handle) if handle else 0
            return "text", max(0, size // 2 - 1)
        if user32.IsClipboardFormatAvailable(CF_DIB) or user32.IsClipboardFormatAvailable(
            CF_BITMAP
        ):
            return "image", 0
        return "other", 0
    finally:
        user32.CloseClipboard()


def element_metadata(control: auto.Control) -> dict[str, str]:
    """Metadata of a UI element. Deliberately never touches Name, Value or text patterns."""
    state = ""
    try:
        toggle = control.GetPattern(auto.PatternId.TogglePattern)
        if toggle:
            state = {0: "off", 1: "on", 2: "indeterminate"}.get(toggle.ToggleState, "")
    except Exception:
        pass
    return {
        "control_type": control.ControlTypeName or "",
        "automation_id": control.AutomationId or "",
        "class_name": control.ClassName or "",
        "framework_id": control.FrameworkId or "",
        "state": state,
    }


def is_password(control: auto.Control | None) -> bool:
    """DeskMate read a property that does not exist; uiautomation exposes IsPassword."""
    if control is None:
        return False
    try:
        return bool(control.IsPassword)
    except Exception:
        try:
            return bool(control.Element.CurrentIsPassword)
        except Exception:
            return False


def browser_domain(hwnd: int) -> str:
    """Host name shown in the address bar, or "" while the user is typing in it.

    Only the Chrome/Edge omnibox (class OmniboxViewViews) is read, never an input box
    on the page. If a browser update renames it, no domain is recorded (fails safe).
    """
    try:
        window = auto.ControlFromHandle(hwnd)
        bar = window.EditControl(searchDepth=12, ClassName=OMNIBOX_CLASS)
        if not bar.Exists(0, 0) or bar.HasKeyboardFocus:
            return ""
        return sanitize.domain(bar.GetValuePattern().Value)
    except Exception:
        return ""


class InputWorker:
    """Turns hook events and clipboard/focus polling into observations for the Recorder."""

    def __init__(self, recorder: Recorder, events: queue.Queue, poll_interval: float = 0.5):
        self.recorder = recorder
        self.events = events
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._burst: dict | None = None
        self._last_cut: datetime | None = None
        self._clip_seq: int | None = None
        self._focus_key: tuple | None = None
        self._in_password = False
        self._last_title: str | None = None
        self._names: dict[int, str] = {}  # process id -> process name

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="input", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        with auto.UIAutomationInitializerInThread():
            next_poll = datetime.now(timezone.utc)
            while not self._stop.is_set():
                self._step("events", self._drain, 0.2)
                now = datetime.now(timezone.utc)
                if now >= next_poll:
                    next_poll = now + timedelta(seconds=self.poll_interval)
                    # separate steps: one failing never stops the others
                    self._step("focus", self._poll_focus_and_browser)
                    self._step("clipboard", self._poll_clipboard)
                self._step("typing", self._flush_typing_if_quiet, now)
            self._flush_typing()

    def _step(self, name: str, func, *args) -> None:
        try:
            func(*args)
        except Exception as exc:  # only the type: messages could carry content
            log.error("input %s failed: %s", name, type(exc).__name__)

    def _app_of(self, hwnd: int) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        name = self._names.get(pid.value)
        if name is None:
            try:
                name = psutil.Process(pid.value).name()
            except psutil.Error:
                name = ""
            if len(self._names) > 500:
                self._names.clear()
            self._names[pid.value] = name
        return name

    def _drain(self, timeout: float) -> None:
        try:
            event = self.events.get(timeout=timeout)
        except queue.Empty:
            return
        while True:
            self._handle(event)
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return

    def _handle(self, event: tuple) -> None:
        kind, when, hwnd = event[0], event[1], event[2]
        app = self._app_of(hwnd)  # the window that had the input when it happened
        if kind == "key":
            burst = self._burst
            if burst is None or burst["app"] != app:
                self._flush_typing()
                self._burst = burst = {"app": app, "start": when, "count": 0}
            burst["count"] += 1
            burst["last"] = when
            burst["password"] = burst.get("password", False) or self._in_password
        elif kind == "click":
            self._on_click(when, event[3], event[4], app)
        else:
            if kind == "ctrl+x":
                self._last_cut = when
            self.recorder.observe(
                OperationTypeObservation(when, kind, app_name=app, in_password=self._in_password)
            )

    def _flush_typing_if_quiet(self, now: datetime) -> None:
        if self._burst and now - self._burst["last"] >= TYPING_PAUSE:
            self._flush_typing()

    def _flush_typing(self) -> None:
        burst, self._burst = self._burst, None
        if burst:
            self.recorder.observe(
                TypingObservation(
                    timestamp=burst["start"],
                    keystrokes=burst["count"],
                    duration_seconds=(burst["last"] - burst["start"]).total_seconds(),
                    is_password=burst["password"],
                    app_name=burst["app"],
                )
            )

    def _on_click(self, when: datetime, x: int, y: int, app: str) -> None:
        control = auto.ControlFromPoint(x, y)
        if control is None:
            return
        self.recorder.observe(
            ControlMetadataObservation(
                when, event_type="click", app_name=app, **element_metadata(control)
            )
        )

    def _poll_focus_and_browser(self) -> None:
        now = datetime.now(timezone.utc)
        app, title = foreground_app()
        focused = auto.GetFocusedControl()
        if focused is not None:
            self._in_password = is_password(focused)
            meta = element_metadata(focused)
            key = (app, tuple(meta.values()))
            if key != self._focus_key:
                self._focus_key = key
                self.recorder.observe(
                    ControlMetadataObservation(now, event_type="focus", app_name=app, **meta)
                )
        if app.lower() in BROWSERS and title != self._last_title:
            self._last_title = title
            domain = browser_domain(win32gui.GetForegroundWindow())
            if domain:
                self.recorder.observe(
                    ControlMetadataObservation(
                        now, event_type="navigate", browser_domain=domain, app_name=app
                    )
                )
        elif app.lower() not in BROWSERS:
            self._last_title = None

    def _poll_clipboard(self) -> None:
        seq = int(user32.GetClipboardSequenceNumber())
        if self._clip_seq is None:
            self._clip_seq = seq
            return
        if seq == self._clip_seq:
            return
        self._clip_seq = seq
        now = datetime.now(timezone.utc)
        app, _ = foreground_app()
        data_type, size = clipboard_shape()
        cut = self._last_cut is not None and now - self._last_cut < timedelta(seconds=2)
        self.recorder.observe(
            ClipboardObservation(now, "cut" if cut else "copy", data_type, size, app_name=app)
        )
