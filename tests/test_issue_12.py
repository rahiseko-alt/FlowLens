import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    ClipboardObservation,
    ControlMetadataObservation,
    OperationTypeObservation,
    TimeRange,
    TypingObservation,
    WindowObservation,
)


def test_delete_by_range_and_scope():
    """範囲（today/last_7_days/last_30_days/all/TimeRange）を指定して削除すると、その範囲の記録だけが消える"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # 1. 40 days ago
        t_40d = now - timedelta(days=40)
        recorder.observe(WindowObservation(timestamp=t_40d, app_name="App40d.exe"))
        recorder.observe(
            WindowObservation(timestamp=t_40d + timedelta(minutes=5), app_name="App40d.exe")
        )

        # 2. 20 days ago
        t_20d = now - timedelta(days=20)
        recorder.observe(WindowObservation(timestamp=t_20d, app_name="App20d.exe"))
        recorder.observe(
            WindowObservation(timestamp=t_20d + timedelta(minutes=5), app_name="App20d.exe")
        )

        # 3. 3 days ago
        t_3d = now - timedelta(days=3)
        recorder.observe(WindowObservation(timestamp=t_3d, app_name="App3d.exe"))
        recorder.observe(
            WindowObservation(timestamp=t_3d + timedelta(minutes=5), app_name="App3d.exe")
        )

        # 4. Today
        t_today = now - timedelta(minutes=30)
        recorder.observe(WindowObservation(timestamp=t_today, app_name="AppToday.exe"))
        recorder.observe(
            WindowObservation(timestamp=now, app_name="AppToday.exe")
        )
        recorder.flush()

        # Delete "today"
        recorder.delete("today")

        export_path = os.path.join(tmpdir, "export1.zip")
        recorder.export(
            time_range=TimeRange(start=t_40d - timedelta(days=1), end=now + timedelta(days=1)),
            password="pwd",
            destination=export_path,
        )
        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        apps = [row[0] for row in conn.execute("SELECT app_name FROM app_sessions").fetchall()]
        conn.close()

        assert "AppToday.exe" not in apps
        assert "App3d.exe" in apps
        assert "App20d.exe" in apps
        assert "App40d.exe" in apps

        # Delete "last_7_days"
        recorder.delete("last_7_days")
        os.remove(export_path)
        recorder.export(
            time_range=TimeRange(start=t_40d - timedelta(days=1), end=now + timedelta(days=1)),
            password="pwd",
            destination=export_path,
        )
        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        apps = [row[0] for row in conn.execute("SELECT app_name FROM app_sessions").fetchall()]
        conn.close()

        assert "App3d.exe" not in apps
        assert "App20d.exe" in apps
        assert "App40d.exe" in apps

        # Delete "all"
        recorder.delete("all")
        os.remove(export_path)
        recorder.export(
            time_range=TimeRange(start=t_40d - timedelta(days=1), end=now + timedelta(days=1)),
            password="pwd",
            destination=export_path,
        )
        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        apps = [row[0] for row in conn.execute("SELECT app_name FROM app_sessions").fetchall()]
        conn.close()

        assert len(apps) == 0


def test_retention_policy_auto_delete():
    """保存期間を過ぎた記録が自動削除で消え、無期限では消えない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)
        recorder.set_retention_days(30)  # 30 days retention

        # 40 days ago
        t_old = now - timedelta(days=40)
        recorder.observe(WindowObservation(timestamp=t_old, app_name="OldApp.exe"))
        recorder.observe(
            WindowObservation(timestamp=t_old + timedelta(minutes=5), app_name="OldApp.exe")
        )
        recorder.observe(TypingObservation(timestamp=t_old, keystrokes=10))

        # 10 days ago
        t_recent = now - timedelta(days=10)
        recorder.observe(WindowObservation(timestamp=t_recent, app_name="RecentApp.exe"))
        recorder.observe(
            WindowObservation(timestamp=t_recent + timedelta(minutes=5), app_name="RecentApp.exe")
        )
        recorder.flush()

        # Trigger retention cleanup
        recorder.apply_retention_policy()

        # Check in storage
        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        apps = [row[0] for row in conn.execute("SELECT app_name FROM app_sessions").fetchall()]
        conn.close()

        assert "OldApp.exe" not in apps
        assert "RecentApp.exe" in apps

        # Set retention to indefinite (None)
        recorder.set_retention_days(None)

        # Insert 100 days old data
        t_ancient = now - timedelta(days=100)
        recorder.observe(WindowObservation(timestamp=t_ancient, app_name="AncientApp.exe"))
        recorder.observe(
            WindowObservation(timestamp=t_ancient + timedelta(minutes=5), app_name="AncientApp.exe")
        )
        recorder.flush()

        recorder.apply_retention_policy()

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        apps = [row[0] for row in conn.execute("SELECT app_name FROM app_sessions").fetchall()]
        conn.close()

        assert "AncientApp.exe" in apps
        assert "RecentApp.exe" in apps


def test_deletion_does_not_fail_with_foreign_keys():
    """削除は外部キーなどで途中で止まらない（DeskMateの不具合回避）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        recorder.observe(WindowObservation(timestamp=now, app_name="App.exe"))
        recorder.observe(TypingObservation(timestamp=now, keystrokes=25))
        recorder.observe(OperationTypeObservation(timestamp=now, operation_type="ctrl+c"))
        recorder.observe(ClipboardObservation(timestamp=now, action="copy", data_type="text"))
        recorder.observe(
            ControlMetadataObservation(timestamp=now, event_type="click", control_type="Button")
        )
        recorder.flush()

        # Enable foreign keys explicitly in connection to ensure no FK constraint error
        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.close()

        # Should complete cleanly without error
        recorder.delete("all")

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        for table in [
            "app_sessions",
            "typing_activities",
            "operation_types",
            "clipboard_transfers",
            "control_events",
            "excluded_intervals",
        ]:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0
        conn.close()


def test_database_size_decreases_after_deletion():
    """削除後にデータ使用量が減る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # Insert lots of records to grow the database file
        for i in range(500):
            t = now - timedelta(minutes=i)
            recorder.observe(WindowObservation(timestamp=t, app_name=f"HeavyApp{i % 10}.exe"))
            recorder.observe(TypingObservation(timestamp=t, keystrokes=50))
            recorder.observe(
                ControlMetadataObservation(
                    timestamp=t,
                    event_type="invoke",
                    control_type="ListItem",
                    automation_id=f"Item_{i}",
                    class_name="ListViewItem",
                )
            )
        recorder.flush()

        db_path = os.path.join(tmpdir, "collector.db")
        # Checkpoint WAL so main DB file reflects size
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.close()
        size_before = os.path.getsize(db_path)

        # Delete all records
        recorder.delete("all")

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.close()
        size_after = os.path.getsize(db_path)

        assert size_after < size_before
