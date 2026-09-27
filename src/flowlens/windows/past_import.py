from __future__ import annotations

import codecs
import os
import re
import shutil
import sqlite3
import struct
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flowlens.core.models import (
    PastAppUsageObservation,
    PastBrowserObservation,
    PastFileObservation,
    PastSystemEventObservation,
)

if TYPE_CHECKING:
    from flowlens.core.recorder import Recorder

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]

try:
    import win32evtlog
except ImportError:
    win32evtlog = None  # type: ignore[assignment]

WINDOWS_EPOCH_1601 = datetime(1601, 1, 1, tzinfo=timezone.utc)

SYSTEM_EVENT_TYPE_MAP = {
    6005: "boot",
    12: "boot",
    6006: "shutdown",
    13: "shutdown",
    1074: "shutdown",
    42: "sleep",
    1: "resume",
    107: "resume",
}

SECURITY_EVENT_TYPE_MAP = {
    4624: "logon",
    4634: "logoff",
    4800: "lock",
    4801: "unlock",
}


def read_system_event_log(max_days: int = 30) -> list[PastSystemEventObservation]:
    """Reads boot/shutdown/sleep/resume events from Windows System Event Log."""
    if win32evtlog is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    observations: list[PastSystemEventObservation] = []

    h_log = win32evtlog.OpenEventLog(None, "System")
    try:
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        while True:
            events = win32evtlog.ReadEventLog(h_log, flags, 0)
            if not events:
                break

            stop = False
            for ev in events:
                # Event ID low 16 bits
                event_id = ev.EventID & 0xFFFF
                ev_time = ev.TimeGenerated.replace(tzinfo=timezone.utc)

                if ev_time < cutoff:
                    stop = True
                    break

                if event_id in SYSTEM_EVENT_TYPE_MAP:
                    event_type = SYSTEM_EVENT_TYPE_MAP[event_id]
                    observations.append(
                        PastSystemEventObservation(
                            event_type=event_type,
                            timestamp=ev_time,
                            source="system_log",
                        )
                    )
            if stop:
                break
    finally:
        win32evtlog.CloseEventLog(h_log)

    return observations


def read_security_event_log(max_days: int = 30) -> list[PastSystemEventObservation]:
    """Reads logon/logoff/lock/unlock events from Windows Security Event Log.

    Requires administrator privilege. Raises PermissionError or pywintypes.error
    if insufficient privileges.
    """
    if win32evtlog is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    observations: list[PastSystemEventObservation] = []

    # This call raises pywintypes.error (1314: privilege not held) for non-admin
    h_log = win32evtlog.OpenEventLog(None, "Security")
    try:
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        while True:
            events = win32evtlog.ReadEventLog(h_log, flags, 0)
            if not events:
                break

            stop = False
            for ev in events:
                event_id = ev.EventID & 0xFFFF
                ev_time = ev.TimeGenerated.replace(tzinfo=timezone.utc)

                if ev_time < cutoff:
                    stop = True
                    break

                if event_id in SECURITY_EVENT_TYPE_MAP:
                    event_type = SECURITY_EVENT_TYPE_MAP[event_id]
                    observations.append(
                        PastSystemEventObservation(
                            event_type=event_type,
                            timestamp=ev_time,
                            source="security_log",
                        )
                    )
            if stop:
                break
    finally:
        win32evtlog.CloseEventLog(h_log)

    return observations


def read_srum(max_days: int = 30) -> list[PastAppUsageObservation]:
    """Reads application resource usage from SRUDB.dat.

    Requires administrator privilege. Raises PermissionError if inaccessible.
    """
    srum_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "sru" / "SRUDB.dat"
    if not srum_path.exists():
        return []

    # Attempt to open SRUDB.dat - non-admin will raise PermissionError (WinError 5)
    with open(srum_path, "rb") as _:
        pass

    # In MVP, if admin access is available, SRUM database parsing would occur here.
    return []


def read_user_assist(max_days: int = 30) -> list[PastAppUsageObservation]:
    """Reads application execution history from HKCU UserAssist registry keys."""
    if winreg is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    observations: list[PastAppUsageObservation] = []
    root_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root_path) as root_key:
            num_subkeys = winreg.QueryInfoKey(root_key)[0]
            for i in range(num_subkeys):
                sub_guid = winreg.EnumKey(root_key, i)
                count_path = rf"{sub_guid}\Count"
                try:
                    with winreg.OpenKey(root_key, count_path) as count_key:
                        num_values = winreg.QueryInfoKey(count_key)[1]
                        for j in range(num_values):
                            val_name, val_data, _ = winreg.EnumValue(count_key, j)
                            if len(val_data) != 72:
                                continue

                            decoded_name = codecs.decode(val_name, "rot_13")
                            # UserAssist 72-byte record:
                            # offset 4: run count (DWORD)
                            # offset 12: focus time in ms (DWORD)
                            # offset 60: last execution FILETIME (QWORD, 64-bit uint)
                            focus_time_ms = struct.unpack_from("<I", val_data, 12)[0]
                            filetime = struct.unpack_from("<Q", val_data, 60)[0]
                            if filetime == 0:
                                continue

                            dt = WINDOWS_EPOCH_1601 + timedelta(microseconds=filetime // 10)
                            if dt < cutoff:
                                continue

                            # Derive application name
                            clean_name = decoded_name.strip()
                            if clean_name.lower().endswith(".lnk"):
                                clean_name = Path(clean_name).stem
                            app_name = Path(clean_name).name
                            if not app_name:
                                continue

                            duration_seconds = focus_time_ms / 1000.0
                            start_time = dt - timedelta(seconds=duration_seconds)
                            observations.append(
                                PastAppUsageObservation(
                                    app_name=app_name,
                                    window_title="",
                                    start_time=start_time,
                                    end_time=dt,
                                    duration_seconds=duration_seconds,
                                    source="user_assist",
                                )
                            )
                except OSError:
                    continue
    except OSError:
        pass

    return observations


def read_recent_files(max_days: int = 30) -> list[PastFileObservation]:
    """Reads recently opened files from %APPDATA%\\Microsoft\\Windows\\Recent."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []

    recent_dir = Path(appdata) / "Microsoft" / "Windows" / "Recent"
    if not recent_dir.is_dir():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    observations: list[PastFileObservation] = []

    try:
        for entry in recent_dir.iterdir():
            if not entry.name.lower().endswith(".lnk"):
                continue

            try:
                mtime = os.path.getmtime(entry)
                dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                if dt < cutoff:
                    continue

                # The .lnk name without '.lnk' suffix represents the target file name
                file_name = entry.name[:-4]
                observations.append(
                    PastFileObservation(
                        file_path=file_name,
                        app_name="",
                        timestamp=dt,
                        source="recent_files",
                    )
                )
            except OSError:
                continue
    except OSError:
        pass

    return observations


def read_office_recent(max_days: int = 30) -> list[PastFileObservation]:
    """Reads recently opened Office documents from HKCU Office MRU registry keys."""
    if winreg is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    observations: list[PastFileObservation] = []
    office_root = r"Software\Microsoft\Office"

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, office_root) as off_key:
            num_vers = winreg.QueryInfoKey(off_key)[0]
            for v_idx in range(num_vers):
                ver_name = winreg.EnumKey(off_key, v_idx)
                for app in ["Word", "Excel", "PowerPoint", "Access"]:
                    app_mru_path = rf"{office_root}\{ver_name}\{app}\User MRU"
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, app_mru_path) as user_mru:
                            num_users = winreg.QueryInfoKey(user_mru)[0]
                            for u_idx in range(num_users):
                                user_sub = winreg.EnumKey(user_mru, u_idx)
                                file_mru_path = rf"{app_mru_path}\{user_sub}\File MRU"
                                try:
                                    with winreg.OpenKey(
                                        winreg.HKEY_CURRENT_USER, file_mru_path
                                    ) as file_mru:
                                        num_items = winreg.QueryInfoKey(file_mru)[1]
                                        for i_idx in range(num_items):
                                            _, item_val, _ = winreg.EnumValue(file_mru, i_idx)
                                            if not isinstance(item_val, str):
                                                continue

                                            # Pattern: [F...][T<FT_HEX>][O...]*C:\Path\to\file.ext
                                            m_file = item_val.split("*", 1)
                                            if len(m_file) < 2:
                                                continue
                                            file_path = m_file[1]

                                            m_time = re.search(r"\[T([0-9A-Fa-f]+)\]", m_file[0])
                                            if m_time:
                                                ft = int(m_time.group(1), 16)
                                                dt = WINDOWS_EPOCH_1601 + timedelta(
                                                    microseconds=ft // 10
                                                )
                                            else:
                                                dt = datetime.now(timezone.utc)

                                            if dt < cutoff:
                                                continue

                                            observations.append(
                                                PastFileObservation(
                                                    file_path=file_path,
                                                    app_name=f"{app}.exe",
                                                    timestamp=dt,
                                                    source="office_recent",
                                                )
                                            )
                                except OSError:
                                    continue
                    except OSError:
                        continue
    except OSError:
        pass

    return observations


def read_browser_history(max_days: int = 30) -> list[PastBrowserObservation]:
    """Reads browser history from Chrome and Edge databases.

    Copies the History SQLite database to a temporary location before querying,
    ensuring it can be read even while browsers are running.
    """
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    cutoff_webkit = int((cutoff - WINDOWS_EPOCH_1601).total_seconds() * 1_000_000)

    observations: list[PastBrowserObservation] = []

    browser_roots = [
        Path(localappdata) / "Google" / "Chrome" / "User Data",
        Path(localappdata) / "Microsoft" / "Edge" / "User Data",
    ]

    for root in browser_roots:
        if not root.is_dir():
            continue

        # Look for Default/History and Profile */History
        history_files: list[Path] = []
        default_hist = root / "Default" / "History"
        if default_hist.is_file():
            history_files.append(default_hist)

        for sub in root.glob("Profile */History"):
            if sub.is_file():
                history_files.append(sub)

        for hist_path in history_files:
            try:
                # Copy to temp directory so open browser locks do not block reading
                with tempfile.TemporaryDirectory() as td:
                    td_path = Path(td)
                    temp_copy = td_path / "History"
                    shutil.copy2(hist_path, temp_copy)

                    # Copy WAL/SHM if present
                    wal_file = hist_path.parent / (hist_path.name + "-wal")
                    if wal_file.is_file():
                        shutil.copy2(wal_file, td_path / "History-wal")
                    shm_file = hist_path.parent / (hist_path.name + "-shm")
                    if shm_file.is_file():
                        shutil.copy2(shm_file, td_path / "History-shm")

                    conn = sqlite3.connect(f"file:{temp_copy}?mode=ro", uri=True)
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT url, last_visit_time FROM urls WHERE last_visit_time > ?",
                            (cutoff_webkit,),
                        )
                        rows = cursor.fetchall()
                        for url_str, last_visit in rows:
                            if not url_str or not last_visit:
                                continue
                            dt = WINDOWS_EPOCH_1601 + timedelta(microseconds=last_visit)
                            observations.append(
                                PastBrowserObservation(
                                    url=url_str,
                                    timestamp=dt,
                                    source="browser_history",
                                )
                            )
                    finally:
                        conn.close()
            except Exception:
                continue

    return observations


def get_windows_past_providers(max_days: int = 30) -> dict[str, Callable[[], list[Any]]]:
    """Returns a dictionary of past data source providers for Windows."""
    return {
        "system_log": lambda: read_system_event_log(max_days),
        "security_log": lambda: read_security_event_log(max_days),
        "srum": lambda: read_srum(max_days),
        "user_assist": lambda: read_user_assist(max_days),
        "recent_files": lambda: read_recent_files(max_days),
        "office_recent": lambda: read_office_recent(max_days),
        "browser_history": lambda: read_browser_history(max_days),
    }


def run_windows_past_import(recorder: Recorder, max_days: int = 30) -> dict[str, dict[str, Any]]:
    """Executes past data import from all available Windows sources into Recorder.

    Returns the per-source import report.
    """
    providers = get_windows_past_providers(max_days)
    return recorder.import_past_providers(providers)
