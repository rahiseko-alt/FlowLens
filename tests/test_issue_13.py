import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    ClipboardObservation,
    IdleObservation,
    TimeRange,
    WindowObservation,
)


def test_summary_generation_live_and_past():
    """偽の観測から期待どおりの合計時間・アプリごとの時間・起動回数・転記回数が過去分と記録分で別々に出る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: t0)

        # Live capture: Chrome (Session 1: 10:00 to 10:10 = 600s)
        recorder.observe(WindowObservation(timestamp=t0, app_name="Chrome.exe"))
        t1 = t0 + timedelta(minutes=10)
        recorder.observe(WindowObservation(timestamp=t1, app_name="Chrome.exe"))

        # Chrome -> Excel copy & paste
        t2 = t1 + timedelta(minutes=1)
        recorder.observe(
            ClipboardObservation(timestamp=t2, action="copy", data_type="text", data_length=50)
        )
        # Excel (Session 1: 10:11 to 10:20 = 540s)
        recorder.observe(WindowObservation(timestamp=t2, app_name="Excel.exe"))
        t3 = t1 + timedelta(minutes=10)
        recorder.observe(
            ClipboardObservation(timestamp=t3, action="paste", data_type="text", data_length=50)
        )
        recorder.observe(WindowObservation(timestamp=t3, app_name="Excel.exe"))

        # Live capture: Chrome (Session 2: 10:20 to 10:25 = 300s)
        t4 = t3 + timedelta(minutes=5)
        recorder.observe(WindowObservation(timestamp=t3, app_name="Chrome.exe"))
        recorder.observe(WindowObservation(timestamp=t4, app_name="Chrome.exe"))
        recorder.flush()

        # Insert some past records into storage directly to simulate Past Import (is_past=1)
        t_past_start = t0 - timedelta(days=2)
        t_past_end = t_past_start + timedelta(minutes=15)
        recorder.storage.insert_app_session(
            app_name="Word.exe",
            window_title_hash="hash_word",
            window_title_ext=".docx",
            start_time=t_past_start,
            end_time=t_past_end,
            duration_seconds=900.0,
            is_past=1,
            source="event_log",
        )
        recorder.storage.insert_clipboard_transfer(
            source_app="Word.exe",
            target_app="Excel.exe",
            data_type="text",
            data_length=100,
            copy_time=t_past_start + timedelta(minutes=5),
            paste_time=t_past_start + timedelta(minutes=6),
            is_past=1,
            source="past_import",
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0 - timedelta(days=5), end=t4 + timedelta(hours=1)),
            password="pwd",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["summary.json"])

        with open(os.path.join(tmpdir, "summary.json"), "r", encoding="utf-8") as f:
            summary = json.load(f)

        assert "total_active_seconds" in summary
        # Live Chrome: 660 (10:00-10:11) + 300 (10:20-10:25) = 960s (2 sessions)
        # Live Excel: 540s (10:11-10:20, 1 session)
        # Past Word: 900s (1 session)
        # Total active = 960 + 540 + 900 = 2400s
        assert summary["total_active_seconds"] == 2400.0

        # Check live section
        live = summary["live"]
        assert live["total_seconds"] == 1500.0
        assert live["apps"]["Chrome.exe"]["duration_seconds"] == 960.0
        assert live["apps"]["Chrome.exe"]["session_count"] == 2
        assert live["apps"]["Excel.exe"]["duration_seconds"] == 540.0
        assert live["apps"]["Excel.exe"]["session_count"] == 1
        assert live["transfers"]["Chrome.exe->Excel.exe"] == 1

        # Check past section
        past = summary["past"]
        assert past["total_seconds"] == 900.0
        assert past["apps"]["Word.exe"]["duration_seconds"] == 900.0
        assert past["apps"]["Word.exe"]["session_count"] == 1
        assert past["transfers"]["Word.exe->Excel.exe"] == 1


def test_summary_excludes_idle_and_excluded_apps():
    """除外中・idle の時間は作業時間に入らない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: t0)
        recorder.set_excluded_apps(["SecretApp.exe"])

        # 1. Normal app (5 min = 300s)
        recorder.observe(WindowObservation(timestamp=t0, app_name="NormalApp.exe"))
        t1 = t0 + timedelta(minutes=5)
        recorder.observe(WindowObservation(timestamp=t1, app_name="NormalApp.exe"))

        # 2. Excluded app (10 min = 600s)
        recorder.observe(WindowObservation(timestamp=t1, app_name="SecretApp.exe"))
        t2 = t1 + timedelta(minutes=10)
        recorder.observe(WindowObservation(timestamp=t2, app_name="SecretApp.exe"))

        # 3. Idle period (15 min = 900s)
        recorder.observe(IdleObservation(timestamp=t2, is_idle=True))
        t3 = t2 + timedelta(minutes=15)
        recorder.observe(IdleObservation(timestamp=t3, is_idle=False))

        # 4. Normal app again (5 min = 300s)
        recorder.observe(WindowObservation(timestamp=t3, app_name="NormalApp.exe"))
        t4 = t3 + timedelta(minutes=5)
        recorder.observe(WindowObservation(timestamp=t4, app_name="NormalApp.exe"))
        recorder.flush()

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t4 + timedelta(minutes=1)),
            password="pwd",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["summary.json"])

        with open(os.path.join(tmpdir, "summary.json"), "r", encoding="utf-8") as f:
            summary = json.load(f)

        # Only NormalApp sessions (300s + 300s = 600s) should count as active work
        assert summary["total_active_seconds"] == 600.0
        assert "SecretApp.exe" not in summary["live"]["apps"]
        assert summary["live"]["apps"]["NormalApp.exe"]["duration_seconds"] == 600.0
        assert summary["live"]["apps"]["NormalApp.exe"]["session_count"] == 2
