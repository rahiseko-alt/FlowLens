"""Hidden window: tray icon, tray menu, and lock / sleep / disconnect notifications.

One hidden top-level window (never shown) lives on the main thread. Windows sends
it session changes (WTS) and power broadcasts, which become Lock/Sleep/Disconnect
observations, and it owns the tray icon that shows whether recording is on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

import win32api
import win32con
import win32gui
import win32ts

from flowlens.core import (
    LockObservation,
    Recorder,
    SessionDisconnectObservation,
    SleepObservation,
)

log = logging.getLogger("flowlens")

WM_TRAY = win32con.WM_APP + 1
WM_OPEN_SETTINGS = win32con.WM_APP + 2  # sent by a second start (e.g. from the Start menu)
WINDOW_CLASS = "FlowLensCollector"
WM_WTSSESSION_CHANGE = 0x02B1
WTS_CONSOLE_CONNECT, WTS_CONSOLE_DISCONNECT = 0x1, 0x2
WTS_REMOTE_CONNECT, WTS_REMOTE_DISCONNECT = 0x3, 0x4
WTS_SESSION_LOCK, WTS_SESSION_UNLOCK = 0x7, 0x8
PBT_APMSUSPEND, PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC = 0x4, 0x7, 0x12

MENU_STATUS, MENU_TOGGLE, MENU_SETTINGS, MENU_EXIT = 1001, 1002, 1003, 1004


class TrayShell:
    def __init__(
        self,
        recorder: Recorder,
        on_status: Callable[[], None],
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        self.recorder = recorder
        self.on_status = on_status
        self.on_settings = on_settings
        self.on_exit = on_exit
        self.hwnd: int | None = None
        self._taskbar_created = win32gui.RegisterWindowMessage("TaskbarCreated")
        self._busy = False

    # ------------------------------------------------------------------ window

    def create(self) -> None:
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = WINDOW_CLASS
        wc.lpfnWndProc = self._wndproc
        win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(
            wc.lpszClassName, "FlowLens", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
        )
        win32ts.WTSRegisterSessionNotification(self.hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)
        self._add_icon()

    def destroy(self) -> None:
        """Removes the icon and the window. Safe to call twice."""
        hwnd, self.hwnd = self.hwnd, None
        if not hwnd:
            return
        for step in (
            lambda: win32ts.WTSUnRegisterSessionNotification(hwnd),
            lambda: win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 0)),
            lambda: win32gui.DestroyWindow(hwnd),
        ):
            try:
                step()
            except Exception:
                pass

    def run(self) -> None:
        """Pumps messages until the tray menu's 終了 is chosen."""
        win32gui.PumpMessages()

    def close(self) -> None:
        """Ends the message loop from any thread (used by the automated check)."""
        if self.hwnd:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)

    def notify(self, title: str, text: str) -> None:
        """A balloon next to the tray icon, so the employee sees where FlowLens lives."""
        try:
            win32gui.Shell_NotifyIcon(
                win32gui.NIM_MODIFY,
                (
                    self.hwnd,
                    0,
                    win32gui.NIF_INFO,
                    WM_TRAY,
                    0,
                    "",
                    text,
                    10,
                    title,
                    win32gui.NIIF_INFO,
                ),
            )
        except win32gui.error as exc:
            log.error("balloon failed: %s", type(exc).__name__)

    def refresh(self) -> None:
        """Updates the icon and tooltip after pause/resume."""
        self._add_icon(modify=True)

    def _icon_data(self) -> tuple:
        paused = self.recorder.is_paused
        icon = win32gui.LoadIcon(0, win32con.IDI_WARNING if paused else win32con.IDI_APPLICATION)
        tip = "FlowLens: 一時停止中" if paused else "FlowLens: 記録中"
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        return (self.hwnd, 0, flags, WM_TRAY, icon, tip)

    def _add_icon(self, modify: bool = False) -> None:
        action = win32gui.NIM_MODIFY if modify else win32gui.NIM_ADD
        try:
            win32gui.Shell_NotifyIcon(action, self._icon_data())
        except win32gui.error:
            if modify:
                win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, self._icon_data())

    # ------------------------------------------------------------------ messages

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_TRAY and lparam in (win32con.WM_RBUTTONUP, win32con.WM_LBUTTONUP):
                self._show_menu()
            elif msg == WM_OPEN_SETTINGS:
                self._on_command(MENU_SETTINGS)
            elif msg == win32con.WM_COMMAND:
                self._on_command(win32api.LOWORD(wparam))
            elif msg == WM_WTSSESSION_CHANGE:
                self._on_session_change(wparam)
            elif msg == win32con.WM_POWERBROADCAST:
                self._on_power(wparam)
                return 1
            elif msg == self._taskbar_created:
                self._add_icon()  # Explorer restarted
            elif msg in (win32con.WM_QUERYENDSESSION, win32con.WM_ENDSESSION):
                self.recorder.flush()
                return 1
            elif msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0
        except Exception as exc:
            log.error("window message %s failed: %s", msg, type(exc).__name__)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _on_session_change(self, event: int) -> None:
        now = datetime.now(timezone.utc)
        observation = {
            WTS_SESSION_LOCK: LockObservation(now, True),
            WTS_SESSION_UNLOCK: LockObservation(now, False),
            WTS_CONSOLE_DISCONNECT: SessionDisconnectObservation(now, True),
            WTS_REMOTE_DISCONNECT: SessionDisconnectObservation(now, True),
            WTS_CONSOLE_CONNECT: SessionDisconnectObservation(now, False),
            WTS_REMOTE_CONNECT: SessionDisconnectObservation(now, False),
        }.get(event)
        if observation is not None:
            self.recorder.observe(observation)

    def _on_power(self, event: int) -> None:
        now = datetime.now(timezone.utc)
        if event == PBT_APMSUSPEND:
            self.recorder.observe(SleepObservation(now, True))
        elif event in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
            self.recorder.observe(SleepObservation(now, False))

    def _show_menu(self) -> None:
        menu = win32gui.CreatePopupMenu()
        toggle = "記録を再開する" if self.recorder.is_paused else "一時停止する"
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_STATUS, "記録の状態を見る")
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_TOGGLE, toggle)
        win32gui.AppendMenu(
            menu, win32con.MF_STRING, MENU_SETTINGS, "設定・削除・診断データの書き出し"
        )
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_EXIT, "FlowLens を終了する")
        x, y = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, x, y, 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)

    def _on_command(self, command: int) -> None:
        if command == MENU_TOGGLE:
            if self.recorder.is_paused:
                self.recorder.resume()
            else:
                self.recorder.pause()
            self.refresh()
        elif command == MENU_EXIT:
            self.on_exit()
            self.destroy()  # WM_DESTROY ends the message loop
        elif command in (MENU_STATUS, MENU_SETTINGS) and not self._busy:
            # Tk windows run their own message loop on this thread, which keeps this
            # window (and the hooks) served while they are open.
            self._busy = True
            try:
                (self.on_status if command == MENU_STATUS else self.on_settings)()
            finally:
                self._busy = False
                self.refresh()
