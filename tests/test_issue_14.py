import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    PastAppUsageObservation,
    PastBrowserObservation,
    PastFileObservation,
    PastSystemEventObservation,
    TimeRange,
)


def test_past_records_distinguished_and_sanitized():
    """過去分は記録分と区別され元が分かり、ファイル名・題名・URLが最小データ原則に従って無害化される"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        t_past = now - timedelta(days=10)

        # 1. Past app usage
        app_obs = PastAppUsageObservation(
            app_name="Excel.exe",
            window_title="ConfidentialClientData.xlsx",
            start_time=t_past,
            end_time=t_past + timedelta(minutes=30),
            duration_seconds=1800.0,
            source="srum",
        )
        # 2. Past system event
        sys_obs = PastSystemEventObservation(
            event_type="boot",
            timestamp=t_past - timedelta(hours=1),
            source="event_log",
        )
        # 3. Past file opened
        file_obs = PastFileObservation(
            file_path=r"C:\Users\JohnDoe\SecretProjects\TopSecretPlan.docx",
            app_name="WINWORD.EXE",
            timestamp=t_past + timedelta(minutes=5),
            source="recent_files",
        )
        # 4. Past browser history
        browser_obs = PastBrowserObservation(
            url="https://admin.portal.example.com/customers/12345?auth=secret_token#profile",
            timestamp=t_past + timedelta(minutes=10),
            source="chrome_history",
        )

        recorder.import_past_records("srum", [app_obs])
        recorder.import_past_records("event_log", [sys_obs])
        recorder.import_past_records("recent_files", [file_obs])
        recorder.import_past_records("chrome_history", [browser_obs])

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=now - timedelta(days=30), end=now),
            password="pwd",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        conn.row_factory = sqlite3.Row

        # Check app_sessions: is_past=1, source="srum"
        sessions = conn.execute("SELECT * FROM app_sessions WHERE is_past = 1").fetchall()
        assert len(sessions) == 1
        assert sessions[0]["app_name"] == "Excel.exe"
        assert sessions[0]["source"] == "srum"
        assert sessions[0]["window_title_ext"] == ".xlsx"

        # Check system_events: is_past=1, source="event_log"
        sys_events = conn.execute("SELECT * FROM system_events").fetchall()
        assert len(sys_events) == 1
        assert sys_events[0]["event_type"] == "boot"
        assert sys_events[0]["source"] == "event_log"

        # Check file_events: is_past=1, source="recent_files"
        file_events = conn.execute("SELECT * FROM file_events").fetchall()
        assert len(file_events) == 1
        assert file_events[0]["app_name"] == "WINWORD.EXE"
        assert file_events[0]["file_ext"] == ".docx"
        assert file_events[0]["source"] == "recent_files"

        # Check browser_events: is_past=1, source="chrome_history"
        browser_events = conn.execute("SELECT * FROM browser_events").fetchall()
        assert len(browser_events) == 1
        assert browser_events[0]["browser_domain"] == "admin.portal.example.com"
        assert browser_events[0]["source"] == "chrome_history"

        conn.close()

        # Check raw database content for sensitive raw strings
        with open(os.path.join(tmpdir, "data.sqlite"), "rb") as f:
            content = f.read()

        assert b"ConfidentialClientData" not in content
        assert b"JohnDoe" not in content
        assert b"SecretProjects" not in content
        assert b"TopSecretPlan" not in content
        assert b"customers/12345" not in content
        assert b"secret_token" not in content


def test_unselected_sources_not_imported():
    """選ばれていない元は読まれない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # Select only srum and recent_files
        recorder.set_enabled_past_sources(["srum", "recent_files"])

        t_past = now - timedelta(days=5)
        file_obs = PastFileObservation(
            file_path="C:\\doc.txt",
            timestamp=t_past,
            source="recent_files",
        )
        browser_obs = PastBrowserObservation(
            url="https://example.com/test",
            timestamp=t_past,
            source="chrome_history",
        )

        res_file = recorder.import_past_records("recent_files", [file_obs])
        res_browser = recorder.import_past_records("chrome_history", [browser_obs])

        assert res_file["count"] == 1
        assert res_browser["count"] == 0
        assert res_browser["status"] == "skipped"

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        browser_cnt = conn.execute("SELECT COUNT(*) FROM browser_events").fetchone()[0]
        file_cnt = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0]
        conn.close()

        assert browser_cnt == 0
        assert file_cnt == 1


def test_single_source_failure_does_not_block_others():
    """1つの元が失敗しても他の元は取り込まれ、元ごとの件数と読めなかった理由が残る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        t_past = now - timedelta(days=5)

        def failing_provider():
            raise PermissionError("Access is denied to EventLog Security")

        def successful_provider():
            return [
                PastFileObservation(file_path="C:\\test.xlsx", timestamp=t_past, source="recent")
            ]

        results = recorder.import_past_providers({
            "security_log": failing_provider,
            "recent_files": successful_provider,
        })

        assert results["security_log"]["status"] == "failed"
        assert results["security_log"]["count"] == 0
        assert "Access is denied" in results["security_log"]["error"]

        assert results["recent_files"]["status"] == "success"
        assert results["recent_files"]["count"] == 1
        assert results["recent_files"]["error"] is None

        # Check that file was imported
        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        count = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0]
        conn.close()
        assert count == 1


def test_incremental_import_deduplication():
    """後から追加で読み込んでも、既に取り込んだ分が二重にならない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        t_past = now - timedelta(days=5)
        obs1 = PastFileObservation(file_path="C:\\file1.txt", timestamp=t_past, source="recent")
        obs2 = PastFileObservation(
            file_path="C:\\file2.txt", timestamp=t_past + timedelta(hours=1), source="recent"
        )

        # First import with obs1
        recorder.import_past_records("recent", [obs1])

        # Second import with obs1 and obs2
        recorder.import_past_records("recent", [obs1, obs2])

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        count = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0]
        conn.close()

        assert count == 2  # obs1 was not duplicated


def test_excluded_app_and_older_than_30_days_filtered():
    """除外アプリの過去分は除かれ、過去30日より古い記録は取り込まない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)
        recorder.set_excluded_apps(["SecretBankApp.exe"])

        # 1. Excluded app within 30 days
        obs_excluded = PastAppUsageObservation(
            app_name="SecretBankApp.exe",
            start_time=now - timedelta(days=10),
            end_time=now - timedelta(days=10) + timedelta(minutes=10),
            duration_seconds=600.0,
            source="srum",
        )
        # 2. Normal app older than 30 days (e.g. 35 days ago)
        obs_old = PastAppUsageObservation(
            app_name="OldApp.exe",
            start_time=now - timedelta(days=35),
            end_time=now - timedelta(days=35) + timedelta(minutes=10),
            duration_seconds=600.0,
            source="srum",
        )
        # 3. Valid normal app (15 days ago)
        obs_valid = PastAppUsageObservation(
            app_name="ValidApp.exe",
            start_time=now - timedelta(days=15),
            end_time=now - timedelta(days=15) + timedelta(minutes=10),
            duration_seconds=600.0,
            source="srum",
        )

        recorder.import_past_records("srum", [obs_excluded, obs_old, obs_valid])

        conn = sqlite3.connect(os.path.join(tmpdir, "collector.db"))
        apps = [row[0] for row in conn.execute("SELECT app_name FROM app_sessions").fetchall()]
        conn.close()

        assert "ValidApp.exe" in apps
        assert "SecretBankApp.exe" not in apps
        assert "OldApp.exe" not in apps
