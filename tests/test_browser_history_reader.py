"""#17: the browser-history reader hands the core host names only.

The reader is plain Python + SQLite, so it runs on any OS against a fake profile.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from flowlens.windows import past_import

EPOCH_1601 = datetime(1601, 1, 1, tzinfo=timezone.utc)


def chrome_time(dt: datetime) -> int:
    return int((dt - EPOCH_1601).total_seconds() * 1_000_000)


def make_history(path, visits):
    path.parent.mkdir(parents=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, last_visit_time INTEGER)")
    conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")
    for i, (url, when) in enumerate(visits, start=1):
        conn.execute("INSERT INTO urls VALUES (?, ?, ?)", (i, url, chrome_time(when)))
        conn.execute("INSERT INTO visits (url, visit_time) VALUES (?, ?)", (i, chrome_time(when)))
    conn.commit()
    conn.close()


def test_only_hosts_of_recent_http_visits(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    make_history(
        tmp_path / "Google" / "Chrome" / "User Data" / "Default" / "History",
        [
            ("https://crm.example.com/customer/123?token=abc#frag", now - timedelta(days=1)),
            ("http://user:pw@intra.example.jp:8080/path", now - timedelta(days=2)),
            ("https://search.example?q=給与", now - timedelta(days=3)),
            ("file:///C:/Users/yamada/secret.txt", now - timedelta(days=1)),
            ("https://old.example/", now - timedelta(days=40)),
        ],
    )
    make_history(
        tmp_path / "Microsoft" / "Edge" / "User Data" / "Profile 1" / "History",
        [("https://edge.example/x", now - timedelta(hours=5))],
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    found = past_import.read_browser_history(max_days=30)

    seen = sorted((o.app_name, o.domain) for o in found)
    assert seen == [
        ("chrome.exe", "crm.example.com"),
        ("chrome.exe", "intra.example.jp"),
        ("chrome.exe", "search.example"),
        ("msedge.exe", "edge.example"),
    ]
    for obs in found:
        assert not set("/?#@:") & set(obs.domain)


def test_unreadable_history_is_reported_not_hidden(tmp_path, monkeypatch):
    bad = tmp_path / "Google" / "Chrome" / "User Data" / "Default" / "History"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"not a database")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with pytest.raises(sqlite3.DatabaseError):
        past_import.read_browser_history()
