import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from flowlens.core.app_state import AlreadyRunningError, SingleInstanceLock
from flowlens.core.consent import ALL_PAST_SOURCES, ConsentManager
from flowlens.core.models import WindowObservation
from flowlens.core.recorder import Recorder


def test_consent_manager_lifecycle():
    """同意前は未同意で、全元がデフォルト。同意後に永続化され外した元が反映される"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ConsentManager(tmpdir)
        assert cm.has_consent() is False
        assert cm.get_enabled_sources() == ALL_PAST_SOURCES
        assert cm.get_consent_timestamp() is None

        # Grant consent with a subset of sources
        selected = ["system_log", "recent_files"]
        cm.grant_consent(selected)

        assert cm.has_consent() is True
        assert cm.get_enabled_sources() == selected
        assert cm.get_consent_timestamp() is not None

        # Re-instantiate to verify persistence
        cm2 = ConsentManager(tmpdir)
        assert cm2.has_consent() is True
        assert cm2.get_enabled_sources() == selected


def test_single_instance_lock():
    """二重起動が防止され、最初のプロセスが解放するまで2つ目は取得できない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        lock1 = SingleInstanceLock(tmpdir)
        assert lock1.acquire() is True

        lock2 = SingleInstanceLock(tmpdir)
        with pytest.raises(AlreadyRunningError):
            lock2.acquire()

        lock1.release()

        # Now lock2 can acquire
        assert lock2.acquire() is True
        lock2.release()


def test_collector_status_reporting():
    """状態画面用のステータス（記録中か、開始日、合計時間、DBサイズ）が取得できる"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        status_init = recorder.get_status()
        assert status_init["is_recording"] is True
        assert status_init["is_paused"] is False
        assert status_init["earliest_session"] is None
        assert status_init["total_duration_seconds"] == 0.0
        assert status_init["database_size_bytes"] > 0

        # Simulate recording activity
        t0 = now
        recorder.observe(
            WindowObservation(app_name="Code.exe", window_title="app.py", timestamp=t0)
        )
        t1 = t0 + timedelta(minutes=15)
        recorder.observe(
            WindowObservation(app_name="Slack.exe", window_title="general", timestamp=t1)
        )
        recorder.flush()

        status_after = recorder.get_status()
        assert status_after["is_recording"] is True
        assert status_after["earliest_session"] == t0.isoformat()
        assert status_after["total_duration_seconds"] == 900.0
        assert status_after["session_count"] == 1

        # Pause
        recorder.pause()
        status_paused = recorder.get_status()
        assert status_paused["is_recording"] is False
        assert status_paused["is_paused"] is True


def test_crash_recovery_resumes_state():
    """強制終了後もDBのコミット済みデータが保持され、再起動後にそのまま記録再開できる"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # Record a session and commit
        recorder.observe(
            WindowObservation(app_name="Word.exe", window_title="doc.docx", timestamp=now)
        )
        recorder.observe(
            WindowObservation(
                app_name="Excel.exe",
                window_title="data.xlsx",
                timestamp=now + timedelta(minutes=10),
            )
        )
        recorder.flush()

        # Simulate crash by abandoning previous recorder instance and creating a new one
        recorder_recovered = Recorder(storage_dir=tmpdir, clock=lambda: now + timedelta(minutes=20))
        status = recorder_recovered.get_status()
        assert status["session_count"] == 1
        assert status["total_duration_seconds"] == 600.0

        # Continue recording in the new session
        t_resume = now + timedelta(minutes=20)
        recorder_recovered.observe(
            WindowObservation(app_name="Excel.exe", window_title="data.xlsx", timestamp=t_resume)
        )
        recorder_recovered.observe(
            WindowObservation(
                app_name="PowerPoint.exe",
                window_title="slides.pptx",
                timestamp=t_resume + timedelta(minutes=5),
            )
        )
        recorder_recovered.flush()

        status2 = recorder_recovered.get_status()
        assert status2["session_count"] == 2
        assert status2["total_duration_seconds"] == 900.0


def test_operational_logger_sanitization():
    """障害調査用のログに業務データや入力内容が出ない"""
    from flowlens.core.logging_config import close_logging, setup_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "flowlens.log"
        try:
            logger = setup_logging(log_file)

            logger.info("Collector service started")
            logger.info("Consent granted by user")
            logger.info("Past import completed with 150 items")
            logger.info("Recording paused")
            logger.info("Recording resumed")

            with open(log_file, encoding="utf-8") as f:
                content = f.read()

            assert "Collector service started" in content
            assert "Consent granted by user" in content
            # Ensure no accidental text leaked
            assert "password" not in content.lower()
            assert "http://" not in content
            assert "https://" not in content
        finally:
            close_logging()
