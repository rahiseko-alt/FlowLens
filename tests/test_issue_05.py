import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import TimeRange, WindowObservation


def test_app_sessions_recorded_and_exported():
    """Chrome -> Excel -> Outlook 観測を流すと App Session が SQLite に入っている"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)

        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 30, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 45, 0, tzinfo=timezone.utc)

        recorder.observe(
            WindowObservation(timestamp=t0, app_name="Chrome.exe", window_title="Google Search")
        )
        recorder.observe(
            WindowObservation(timestamp=t1, app_name="Excel.exe", window_title="Report.xlsx")
        )
        recorder.observe(
            WindowObservation(timestamp=t2, app_name="Outlook.exe", window_title="Inbox")
        )
        recorder.observe(
            WindowObservation(timestamp=t3, app_name="Outlook.exe", window_title="Inbox - End")
        )

        export_path = os.path.join(tmpdir, "export.zip")
        password = "secret-password-123"
        result_path = recorder.export(
            time_range=TimeRange(start=t0 - timedelta(hours=1), end=t3 + timedelta(hours=1)),
            password=password,
            destination=export_path,
        )

        assert os.path.exists(result_path)

        with pyzipper.AESZipFile(result_path) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.extractall(path=tmpdir, members=["data.sqlite", "manifest.json"])

        exported_db = os.path.join(tmpdir, "data.sqlite")
        conn = sqlite3.connect(exported_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT app_name, start_time, end_time, duration_seconds "
            "FROM app_sessions ORDER BY start_time ASC"
        )
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) >= 3
        assert rows[0][0] == "Chrome.exe"
        assert rows[0][3] == 900.0  # 15 minutes
        assert rows[1][0] == "Excel.exe"
        assert rows[1][3] == 900.0
        assert rows[2][0] == "Outlook.exe"


def test_encryption_and_manifest():
    """暗号化と manifest.json の検証"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="Chrome.exe"))
        recorder.observe(WindowObservation(timestamp=t1, app_name="Chrome.exe"))

        export_path = os.path.join(tmpdir, "export.zip")
        password = "test-password"
        recorder.export(
            time_range=TimeRange(start=t0, end=t1),
            password=password,
            destination=export_path,
        )

        # パスワードなしでは読めない
        with pytest.raises(Exception):
            with pyzipper.AESZipFile(export_path) as zf:
                zf.read("manifest.json")

        # 正しいパスワードで開く
        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(password.encode("utf-8"))
            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))

        assert "version" in manifest_data
        assert "time_range" in manifest_data
        assert "counts" in manifest_data
        assert "machine_id" in manifest_data
        uuid.UUID(manifest_data["machine_id"])

        manifest_str = json.dumps(manifest_data)
        login_user = os.environ.get("USERNAME") or os.environ.get("USER", "")
        computer_name = os.environ.get("COMPUTERNAME", "")
        if login_user:
            assert login_user.lower() not in manifest_str.lower()
        if computer_name:
            assert computer_name.lower() not in manifest_str.lower()


def test_filter_outside_timerange():
    """指定期間外の記録は含まれない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 20, 10, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)

        recorder.observe(WindowObservation(timestamp=t0, app_name="OldApp.exe"))
        recorder.observe(WindowObservation(timestamp=t1, app_name="OldApp.exe"))
        recorder.observe(WindowObservation(timestamp=t2, app_name="NewApp.exe"))
        recorder.observe(WindowObservation(timestamp=t3, app_name="NewApp.exe"))

        export_path = os.path.join(tmpdir, "export.zip")
        password = "test-password"
        recorder.export(
            time_range=TimeRange(
                start=datetime(2026, 9, 26, 0, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 9, 28, 0, 0, 0, tzinfo=timezone.utc),
            ),
            password=password,
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute("SELECT app_name FROM app_sessions")
        apps = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "NewApp.exe" in apps
        assert "OldApp.exe" not in apps


def test_sqlite_wal_and_schema_version():
    """保存は SQLite（WAL）で、スキーマの版を持つ"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        db_path = recorder.db_path
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"

        cursor.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]
        assert version >= 1
        conn.close()


def test_no_network_communication_dependencies():
    """中核の依存に通信する部品が無い"""
    import flowlens.core

    core_dir = Path(flowlens.core.__file__).parent
    disallowed = [
        "requests", "httpx", "urllib3", "aiohttp", "fastapi", "flask",
        "uvicorn", "websockets", "openai", "anthropic", "google-genai",
        "google.generativeai", "ollama", "socket", "urllib.request", "http.client",
    ]
    for root, _, files in os.walk(core_dir):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    content = f.read()
                    for dis in disallowed:
                        assert f"import {dis}" not in content
                        assert f"from {dis}" not in content
