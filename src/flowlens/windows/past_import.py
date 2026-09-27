"""Past Import readers: footprints Windows already kept for the last 30 days (ADR 0004).

Each reader returns observations and raises on failure; the core records the failure
as a short code and carries on with the other sources. Readers never hand the core a
full URL, and they skip entries without a real timestamp instead of inventing one.
"""

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
from typing import Any

from flowlens.core.models import (
    PastAppStatsObservation,
    PastBrowserObservation,
    PastFileObservation,
    PastSystemEventObservation,
)

try:
    import winreg
except ImportError:  # imported on another OS only by accident; readers then fail cleanly
    winreg = None  # type: ignore[assignment]

try:
    import win32evtlog
except ImportError:
    win32evtlog = None  # type: ignore[assignment]

EPOCH_1601 = datetime(1601, 1, 1, tzinfo=timezone.utc)

# (event source, event id) -> event type. Ids alone are ambiguous across sources.
SYSTEM_EVENTS = {
    ("EventLog", 6005): "boot",
    ("EventLog", 6006): "shutdown",
    ("Microsoft-Windows-Kernel-General", 12): "boot",
    ("Microsoft-Windows-Kernel-General", 13): "shutdown",
    ("User32", 1074): "shutdown",
    ("Microsoft-Windows-Kernel-Power", 42): "sleep",
    ("Microsoft-Windows-Kernel-Power", 107): "resume",
    ("Microsoft-Windows-Power-Troubleshooter", 1): "resume",
}
SECURITY_EVENTS = {
    ("Microsoft-Windows-Security-Auditing", 4800): "lock",
    ("Microsoft-Windows-Security-Auditing", 4801): "unlock",
    ("Microsoft-Windows-Security-Auditing", 4647): "logoff",
}
OFFICE_APPS = {
    "Word": "winword.exe",
    "Excel": "excel.exe",
    "PowerPoint": "powerpnt.exe",
    "Access": "msaccess.exe",
}
BROWSERS = {
    "chrome.exe": ("Google", "Chrome", "User Data"),
    "msedge.exe": ("Microsoft", "Edge", "User Data"),
}

# Host part of http(s) URLs, cut down inside SQLite (path, query, fragment,
# user:password@ and :port removed) so no other part of a URL reaches Python.
_HOST_SQL = """
WITH a AS (
    SELECT substr(u.url, instr(u.url, '://') + 3) AS r, vi.visit_time AS t
    FROM visits vi JOIN urls u ON u.id = vi.url
    WHERE vi.visit_time > ? AND (u.url LIKE 'http://%' OR u.url LIKE 'https://%')
),
b AS (SELECT substr(r, 1, instr(r || '/', '/') - 1) AS r, t FROM a),
c AS (SELECT substr(r, 1, instr(r || '?', '?') - 1) AS r, t FROM b),
d AS (SELECT substr(r, 1, instr(r || '#', '#') - 1) AS r, t FROM c),
e AS (SELECT substr(r, instr(r, '@') + 1) AS r, t FROM d)
SELECT substr(r, 1, instr(r || ':', ':') - 1), t FROM e
"""


def _cutoff(max_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max_days)


def _as_utc(value: datetime) -> datetime:
    """pywin32 returns aware times in recent versions; a naive one is taken as local time."""
    return value.astimezone(timezone.utc)


def _require(module: Any, name: str) -> Any:
    if module is None:
        raise RuntimeError(f"{name} unavailable")
    return module


def _read_event_log(
    log: str, mapping: dict[tuple[str, int], str], source: str, max_days: int
) -> list[PastSystemEventObservation]:
    evt = _require(win32evtlog, "win32evtlog")
    cutoff = _cutoff(max_days)
    found: list[PastSystemEventObservation] = []
    handle = evt.OpenEventLog(None, log)
    try:
        flags = evt.EVENTLOG_BACKWARDS_READ | evt.EVENTLOG_SEQUENTIAL_READ
        while True:
            events = evt.ReadEventLog(handle, flags, 0)
            if not events:
                return found
            for ev in events:
                when = _as_utc(ev.TimeGenerated)
                if when < cutoff:
                    return found
                kind = mapping.get((ev.SourceName, ev.EventID & 0xFFFF))
                if kind:
                    found.append(PastSystemEventObservation(kind, when, source))
    finally:
        evt.CloseEventLog(handle)


def read_system_event_log(max_days: int = 30) -> list[PastSystemEventObservation]:
    """Boot, shutdown, sleep and resume times. Readable without administrator rights."""
    return _read_event_log("System", SYSTEM_EVENTS, "system_log", max_days)


def read_security_event_log(max_days: int = 30) -> list[PastSystemEventObservation]:
    """Lock, unlock and logoff times. Needs administrator rights (fails otherwise)."""
    return _read_event_log("Security", SECURITY_EVENTS, "security_log", max_days)


def read_user_assist(max_days: int = 30) -> list[PastAppStatsObservation]:
    """Per-app counters Explorer keeps: run count, total focus time, last run.

    Only entries that name an executable are used; entries for documents and
    shortcuts are skipped because their names can be anything the user typed.
    """
    reg = _require(winreg, "winreg")
    cutoff = _cutoff(max_days)
    found: list[PastAppStatsObservation] = []
    root_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
    with reg.OpenKey(reg.HKEY_CURRENT_USER, root_path) as root:
        for i in range(reg.QueryInfoKey(root)[0]):
            try:
                count_key = reg.OpenKey(root, rf"{reg.EnumKey(root, i)}\Count")
            except OSError:
                continue
            with count_key:
                for j in range(reg.QueryInfoKey(count_key)[1]):
                    name, data, _ = reg.EnumValue(count_key, j)
                    exe = codecs.decode(name, "rot_13").replace("/", "\\").split("\\")[-1]
                    if not exe.lower().endswith(".exe") or len(data) != 72:
                        continue
                    runs = struct.unpack_from("<I", data, 4)[0]
                    focus_ms = struct.unpack_from("<I", data, 12)[0]
                    filetime = struct.unpack_from("<Q", data, 60)[0]
                    if not filetime:
                        continue
                    last = EPOCH_1601 + timedelta(microseconds=filetime // 10)
                    if last >= cutoff:
                        found.append(
                            PastAppStatsObservation(exe, last, runs, focus_ms / 1000, "user_assist")
                        )
    return found


def read_recent_files(max_days: int = 30) -> list[PastFileObservation]:
    """Files opened recently, from the shortcuts in the Recent folder (not jump lists)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA not set")
    cutoff = _cutoff(max_days)
    found: list[PastFileObservation] = []
    for entry in (Path(appdata) / "Microsoft" / "Windows" / "Recent").glob("*.lnk"):
        try:
            when = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if when >= cutoff:
            found.append(PastFileObservation(entry.name[:-4], when, "", "recent_files"))
    return found


def read_office_recent(max_days: int = 30) -> list[PastFileObservation]:
    """Office "recent documents" lists. Entries without a timestamp are skipped."""
    reg = _require(winreg, "winreg")
    cutoff = _cutoff(max_days)
    found: list[PastFileObservation] = []
    office = r"Software\Microsoft\Office"
    with reg.OpenKey(reg.HKEY_CURRENT_USER, office) as versions:
        for v in range(reg.QueryInfoKey(versions)[0]):
            version = reg.EnumKey(versions, v)
            for app, exe in OFFICE_APPS.items():
                for mru in _office_mru_keys(reg, rf"{office}\{version}\{app}"):
                    for value in mru:
                        head, _, path = value.partition("*")
                        stamp = re.search(r"\[T([0-9A-Fa-f]+)\]", head)
                        if not path or not stamp:
                            continue
                        when = EPOCH_1601 + timedelta(microseconds=int(stamp.group(1), 16) // 10)
                        if when >= cutoff:
                            found.append(PastFileObservation(path, when, exe, "office_recent"))
    return found


def _office_mru_keys(reg: Any, app_path: str) -> list[list[str]]:
    lists: list[list[str]] = []
    candidates = [rf"{app_path}\File MRU"]
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, rf"{app_path}\User MRU") as users:
            for u in range(reg.QueryInfoKey(users)[0]):
                candidates.append(rf"{app_path}\User MRU\{reg.EnumKey(users, u)}\File MRU")
    except OSError:
        pass
    for path in candidates:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, path) as key:
                values = [reg.EnumValue(key, i)[1] for i in range(reg.QueryInfoKey(key)[1])]
                lists.append([v for v in values if isinstance(v, str)])
        except OSError:
            continue
    return lists


def read_browser_history(max_days: int = 30) -> list[PastBrowserObservation]:
    """Visited hosts from Chrome and Edge profiles.

    Each History database is copied first (the browser keeps it locked) and the copy
    is deleted right after. Only the host part leaves SQLite.
    """
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA not set")
    cutoff = int((_cutoff(max_days) - EPOCH_1601).total_seconds() * 1_000_000)
    found: list[PastBrowserObservation] = []
    errors: list[Exception] = []
    files = 0
    for exe, parts in BROWSERS.items():
        root = Path(local).joinpath(*parts)
        for history in [root / "Default" / "History", *root.glob("Profile */History")]:
            if not history.is_file():
                continue
            files += 1
            try:
                found.extend(_read_history(history, cutoff, exe))
            except Exception as exc:
                errors.append(exc)
    if errors and len(errors) == files:
        raise errors[0]
    return found


def _read_history(history: Path, cutoff: int, exe: str) -> list[PastBrowserObservation]:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "History"
        shutil.copy2(history, copy)
        for suffix in ("-wal", "-journal"):
            side = history.with_name(history.name + suffix)
            if side.is_file():
                shutil.copy2(side, copy.with_name(copy.name + suffix))
        conn = sqlite3.connect(copy)
        try:
            rows = conn.execute(_HOST_SQL, (cutoff,)).fetchall()
        finally:
            conn.close()
    found = []
    for host, visit in rows:
        if host and visit:
            when = EPOCH_1601 + timedelta(microseconds=visit)
            found.append(PastBrowserObservation(host, when, exe, "browser_history"))
    return found


READERS: dict[str, Callable[[int], list[Any]]] = {
    "system_log": read_system_event_log,
    "security_log": read_security_event_log,
    "user_assist": read_user_assist,
    "recent_files": read_recent_files,
    "office_recent": read_office_recent,
    "browser_history": read_browser_history,
}


def windows_past_providers(max_days: int = 30) -> dict[str, Callable[[], list[Any]]]:
    return {name: (lambda reader=reader: reader(max_days)) for name, reader in READERS.items()}
