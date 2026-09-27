import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyzipper

from flowlens.core.config import ConfigManager
from flowlens.core.models import WindowObservation
from flowlens.core.recorder import Recorder


def test_config_manager_persistence():
    """除外アプリの追加・削除、保存期間（30/60/90/無期限）が永続化される"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ConfigManager(tmpdir)
        assert cm.get_excluded_apps() == []
        assert cm.get_retention_days() == 30  # Default 30 days

        # Add excluded apps
        cm.add_excluded_app("Slack.exe")
        cm.add_excluded_app("1Password.exe")
        assert set(cm.get_excluded_apps()) == {"slack.exe", "1password.exe"}

        # Remove an app
        cm.remove_excluded_app("slack.exe")
        assert cm.get_excluded_apps() == ["1password.exe"]

        # Change retention days: 30, 60, 90, None (indefinite)
        cm.set_retention_days(60)
        assert cm.get_retention_days() == 60
        cm.set_retention_days(None)
        assert cm.get_retention_days() is None

        # Re-instantiate from disk
        cm2 = ConfigManager(tmpdir)
        assert cm2.get_excluded_apps() == ["1password.exe"]
        assert cm2.get_retention_days() is None


def test_excluded_app_immediate_effect():
    """除外アプリを追加すると即座に記録が無害化され、削除すると記録が再開される"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # 1. Normal recording
        t0 = now
        recorder.observe(
            WindowObservation(app_name="BankApp.exe", window_title="Accounts", timestamp=t0)
        )
        t1 = t0 + timedelta(minutes=5)
        recorder.observe(
            WindowObservation(app_name="BankApp.exe", window_title="Accounts", timestamp=t1)
        )
        recorder.flush()

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        normal_sessions = conn.execute(
            "SELECT * FROM app_sessions WHERE app_name = 'BankApp.exe'"
        ).fetchall()
        conn.close()
        assert len(normal_sessions) == 1

        # 2. Add to excluded apps -> immediately effective
        recorder.add_excluded_app("BankApp.exe")
        t2 = t1 + timedelta(minutes=5)
        t3 = t2 + timedelta(minutes=5)
        recorder.observe(
            WindowObservation(app_name="BankApp.exe", window_title="Accounts", timestamp=t2)
        )
        recorder.observe(
            WindowObservation(app_name="BankApp.exe", window_title="Accounts", timestamp=t3)
        )
        recorder.flush()

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        excluded_rows = conn.execute("SELECT * FROM excluded_intervals").fetchall()
        conn.close()
        assert len(excluded_rows) == 1

        # 3. Remove from excluded apps -> immediately records again
        recorder.remove_excluded_app("BankApp.exe")
        t4 = t3 + timedelta(minutes=5)
        t5 = t4 + timedelta(minutes=5)
        recorder.observe(
            WindowObservation(app_name="BankApp.exe", window_title="Accounts", timestamp=t4)
        )
        recorder.observe(
            WindowObservation(app_name="BankApp.exe", window_title="Accounts", timestamp=t5)
        )
        recorder.flush()

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        after_sessions = conn.execute(
            "SELECT * FROM app_sessions WHERE app_name = 'BankApp.exe'"
        ).fetchall()
        conn.close()
        assert len(after_sessions) == 2


def test_retention_period_options():
    """保存期間を 30／60／90日／無期限から選べ、設定に合わせて古い記録が消える"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # Insert sessions of various ages: 10 days ago, 45 days ago, 75 days ago, 100 days ago
        for days_ago in [10, 45, 75, 100]:
            t_start = now - timedelta(days=days_ago)
            t_end = t_start + timedelta(minutes=30)
            recorder.storage.insert_app_session(
                app_name="App.exe",
                window_title_hash="hash",
                window_title_ext=".txt",
                start_time=t_start,
                end_time=t_end,
                duration_seconds=1800.0,
            )

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        assert conn.execute("SELECT COUNT(*) FROM app_sessions").fetchone()[0] == 4
        conn.close()

        # Set to 90 days -> 100 days ago session removed
        recorder.set_retention_days(90)
        recorder.apply_retention_policy()
        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        assert conn.execute("SELECT COUNT(*) FROM app_sessions").fetchone()[0] == 3
        conn.close()

        # Set to 60 days -> 75 days ago session removed
        recorder.set_retention_days(60)
        recorder.apply_retention_policy()
        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        assert conn.execute("SELECT COUNT(*) FROM app_sessions").fetchone()[0] == 2
        conn.close()

        # Set to 30 days -> 45 days ago session removed
        recorder.set_retention_days(30)
        recorder.apply_retention_policy()
        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        assert conn.execute("SELECT COUNT(*) FROM app_sessions").fetchone()[0] == 1
        conn.close()

        # Set to indefinite (None) -> keeps existing
        recorder.set_retention_days(None)
        recorder.apply_retention_policy()
        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        assert conn.execute("SELECT COUNT(*) FROM app_sessions").fetchone()[0] == 1
        conn.close()


def test_export_period_presets_and_handover():
    """書き出し期間（過去7／14／30日／すべて／日付指定）が手元のファイルに保存される"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # Record sessions
        t0 = now - timedelta(days=20)
        recorder.observe(
            WindowObservation(app_name="App.exe", window_title="doc.docx", timestamp=t0)
        )
        t1 = now - timedelta(days=5)
        recorder.observe(
            WindowObservation(app_name="App.exe", window_title="doc.docx", timestamp=t1)
        )
        recorder.observe(
            WindowObservation(app_name="App.exe", window_title="doc.docx", timestamp=now)
        )
        recorder.flush()

        # Helper method on Recorder: compute_time_range
        tr_7 = recorder.compute_export_range("last_7_days")
        assert tr_7.start == now - timedelta(days=7)

        tr_14 = recorder.compute_export_range("last_14_days")
        assert tr_14.start == now - timedelta(days=14)

        tr_30 = recorder.compute_export_range("last_30_days")
        assert tr_30.start == now - timedelta(days=30)

        tr_all = recorder.compute_export_range("all")
        assert tr_all.start == datetime.min.replace(tzinfo=timezone.utc)

        # Date range
        custom_start = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        custom_end = datetime(2026, 9, 10, 23, 59, 59, tzinfo=timezone.utc)
        tr_custom = recorder.compute_export_range("custom", custom_start, custom_end)
        assert tr_custom.start == custom_start
        assert tr_custom.end == custom_end

        # Export to a user directory (e.g. desktop/downloads), not AppData
        user_dest = Path(tmpdir) / "Desktop" / "flowlens_export.zip"
        exported_path = recorder.export(
            time_range=tr_30,
            password="pwd",
            destination=user_dest,
        )

        assert exported_path == user_dest
        assert exported_path.exists()

        with pyzipper.AESZipFile(exported_path) as zf:
            zf.setpassword(b"pwd")
            assert "data.sqlite" in zf.namelist()
            assert "summary.json" in zf.namelist()
            assert "README.txt" in zf.namelist()
