"""Shared fixtures. Tests talk to the core only through Recorder and the exported file."""

from __future__ import annotations

import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pyzipper

from flowlens.core import Recorder, TimeRange

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
PASSWORD = "correct horse"


class Clock:
    def __init__(self, now: datetime = T0 + timedelta(days=5)):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Export:
    """An opened Diagnostic Export."""

    def __init__(self, path: Path, members: dict[str, bytes], tmp: Path):
        self.path = path
        self.members = members
        db = tmp / "exported.sqlite"
        db.write_bytes(members["data.sqlite"])
        self.db = sqlite3.connect(db)
        self.db.row_factory = sqlite3.Row

    def json(self, name: str):
        return json.loads(self.members[name])

    def rows(self, sql: str, *params):
        return [dict(r) for r in self.db.execute(sql, params)]

    def contains(self, text: str) -> bool:
        """True if `text` appears in any exported file (UTF-8 or UTF-16)."""
        needles = [text.encode("utf-8"), text.encode("utf-16-le")]
        return any(n in blob for blob in self.members.values() for n in needles)


def open_export(path: Path, tmp: Path, password: str = PASSWORD) -> Export:
    with pyzipper.AESZipFile(path) as zf:
        zf.setpassword(password.encode())
        members = {name: zf.read(name) for name in zf.namelist()}
    return Export(path, members, tmp)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def recorder(tmp_path: Path, clock: Clock) -> Recorder:
    return Recorder(tmp_path / "data", clock=clock)


@pytest.fixture
def export(recorder: Recorder, tmp_path: Path):
    """export() -> Export for the whole stored period (or a given range)."""
    counter = iter(range(1000))

    def run(time_range: TimeRange | None = None, password: str = PASSWORD) -> Export:
        # The session in progress is not exported; end it first, as closing the app would.
        recorder.flush()
        rng = time_range or TimeRange(T0 - timedelta(days=60), T0 + timedelta(days=60))
        dest = tmp_path / "out" / f"export{next(counter)}.zip"
        recorder.export(rng, password, dest)
        return open_export(dest, tmp_path, password)

    return run


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def use(recorder, app: str, start: int, end: int, title: str = "") -> None:
    """The watcher reports the foreground window every minute from `start` to `end`."""
    from flowlens.core import WindowObservation

    for minute in range(start, end + 1):
        recorder.observe(WindowObservation(timestamp=at(minute), app_name=app, window_title=title))


__all__ = ["T0", "PASSWORD", "Clock", "Export", "open_export", "at", "use", "io"]
