import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    ClipboardObservation,
    ControlMetadataObservation,
    TimeRange,
    TypingObservation,
    WindowObservation,
)


def test_excluded_app_recorded_only_as_excluded_duration():
    """除外アプリの観測を流しても、書き出したファイルにそのアプリの操作・Clipboard・URL・題名が無く、除外中の時間だけがある"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        recorder.set_excluded_apps(["SecretApp.exe", "1password.exe"])

        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 15, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 20, 0, tzinfo=timezone.utc)

        # Chrome (5 min)
        recorder.observe(
            WindowObservation(timestamp=t0, app_name="Chrome.exe", window_title="Work")
        )
        # SecretApp (10 min, excluded)
        recorder.observe(
            WindowObservation(
                timestamp=t1, app_name="SecretApp.exe", window_title="SuperSecretVault"
            )
        )
        recorder.observe(
            TypingObservation(timestamp=t1, keystrokes=20, duration_seconds=5.0)
        )
        recorder.observe(
            ControlMetadataObservation(timestamp=t1, event_type="click", control_type="Button")
        )
        # Chrome again (5 min)
        recorder.observe(
            WindowObservation(timestamp=t2, app_name="Chrome.exe", window_title="Work")
        )
        recorder.observe(
            WindowObservation(timestamp=t3, app_name="Chrome.exe", window_title="Work")
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t3), password="pwd", destination=export_path
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(
                path=tmpdir,
                members=["data.sqlite", "manifest.json", "redaction_report.json"],
            )

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()

        # Check app_sessions
        cursor.execute("SELECT app_name FROM app_sessions")
        apps = [row[0] for row in cursor.fetchall()]
        assert "SecretApp.exe" not in apps
        assert "Chrome.exe" in apps

        # Check excluded_intervals
        cursor.execute("SELECT duration_seconds FROM excluded_intervals")
        intervals = [row[0] for row in cursor.fetchall()]
        assert 600.0 in intervals  # 10:05 to 10:15 = 10 min = 600s

        # Check that typing and controls for SecretApp are not stored
        cursor.execute("SELECT app_name FROM typing_activities")
        assert "SecretApp.exe" not in [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT app_name FROM control_events")
        assert "SecretApp.exe" not in [row[0] for row in cursor.fetchall()]
        conn.close()

        # Check raw zip contents
        with open(os.path.join(tmpdir, "data.sqlite"), "rb") as f:
            content = f.read()
        assert b"SecretApp" not in content
        assert b"SuperSecretVault" not in content


def test_clipboard_transfer_redacted_if_source_or_target_excluded():
    """Clipboard Transfer の元か先が除外アプリなら、その件は残らない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        recorder.set_excluded_apps(["Keepass.exe"])

        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 2, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 3, 0, tzinfo=timezone.utc)

        # Copy from Keepass (excluded) -> Paste to Browser
        recorder.observe(WindowObservation(timestamp=t0, app_name="Keepass.exe"))
        recorder.observe(
            ClipboardObservation(timestamp=t1, action="copy", data_type="text", data_length=20)
        )
        recorder.observe(WindowObservation(timestamp=t2, app_name="Browser.exe"))
        recorder.observe(
            ClipboardObservation(timestamp=t3, action="paste", data_type="text", data_length=20)
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t3), password="pwd", destination=export_path
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute("SELECT source_app, target_app FROM clipboard_transfers")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 0


def test_pause_and_resume():
    """一時停止から再開までの観測は残らない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 15, 0, tzinfo=timezone.utc)
        t4 = datetime(2026, 9, 27, 10, 20, 0, tzinfo=timezone.utc)

        recorder.observe(WindowObservation(timestamp=t0, app_name="AppBeforePause.exe"))
        recorder.observe(WindowObservation(timestamp=t1, app_name="AppBeforePause.exe"))

        recorder.pause()
        assert recorder.is_paused

        # During pause
        recorder.observe(WindowObservation(timestamp=t2, app_name="PrivateApp.exe"))
        recorder.observe(TypingObservation(timestamp=t2, keystrokes=50))

        recorder.resume()
        assert not recorder.is_paused

        # After resume
        recorder.observe(WindowObservation(timestamp=t3, app_name="AppAfterResume.exe"))
        recorder.observe(WindowObservation(timestamp=t4, app_name="AppAfterResume.exe"))

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t4), password="pwd", destination=export_path
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute("SELECT app_name FROM app_sessions")
        apps = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "AppBeforePause.exe" in apps
        assert "AppAfterResume.exe" in apps
        assert "PrivateApp.exe" not in apps


def test_post_hoc_exclusion_and_redaction_report():
    """保存後に除外を追加した場合も除かれ、redaction_report.json に件数だけが入る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)

        # 録画時には除外設定なしで記録
        recorder.observe(WindowObservation(timestamp=t0, app_name="ConfidentialTool.exe"))
        recorder.observe(WindowObservation(timestamp=t1, app_name="ConfidentialTool.exe"))
        recorder.observe(WindowObservation(timestamp=t1, app_name="GeneralTool.exe"))
        recorder.observe(WindowObservation(timestamp=t2, app_name="GeneralTool.exe"))

        # 書き出し直前に除外設定を追加
        recorder.set_excluded_apps(["ConfidentialTool.exe"])

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t2), password="pwd", destination=export_path
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite", "redaction_report.json"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute("SELECT app_name FROM app_sessions")
        apps = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "GeneralTool.exe" in apps
        assert "ConfidentialTool.exe" not in apps

        with open(os.path.join(tmpdir, "redaction_report.json"), "r", encoding="utf-8") as f:
            report = json.load(f)

        assert "total_redacted_records" in report
        assert report["total_redacted_records"] >= 1
        # 中身（アプリ名やテキスト）が含まれないこと
        report_str = json.dumps(report)
        assert "ConfidentialTool" not in report_str
