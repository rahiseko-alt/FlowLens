import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    IdleObservation,
    LockObservation,
    SessionDisconnectObservation,
    SleepObservation,
    TimeRange,
    WindowObservation,
)


def test_idle_splits_app_session_and_excludes_idle_time():
    """App Session の途中に5分の idle を挟むと、App Session が分かれ、idle の時間を含まない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        recorder.set_idle_threshold_seconds(300.0)

        # 10:00 Chrome 開始
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        # 10:10 Chrome で作業継続
        t1 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)
        # 10:10 に idle 開始（10:10 から 10:15 の5分間放置）
        t_idle_start = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)
        t_idle_end = datetime(2026, 9, 27, 10, 15, 0, tzinfo=timezone.utc)
        # 10:15 に復帰し Chrome で作業再開
        t2 = datetime(2026, 9, 27, 10, 15, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 25, 0, tzinfo=timezone.utc)

        recorder.observe(WindowObservation(timestamp=t0, app_name="Chrome.exe"))
        recorder.observe(WindowObservation(timestamp=t1, app_name="Chrome.exe"))
        recorder.observe(IdleObservation(timestamp=t_idle_start, is_idle=True))
        recorder.observe(IdleObservation(timestamp=t_idle_end, is_idle=False))
        recorder.observe(WindowObservation(timestamp=t2, app_name="Chrome.exe"))
        recorder.observe(WindowObservation(timestamp=t3, app_name="Chrome.exe"))

        export_path = os.path.join(tmpdir, "export.zip")
        password = "test-password"
        recorder.export(
            time_range=TimeRange(start=t0, end=t3),
            password=password,
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT start_time, end_time, duration_seconds FROM app_sessions "
            "ORDER BY start_time ASC"
        )
        sessions = cursor.fetchall()
        conn.close()

        # 2つのセッションに分かれ、それぞれ10分（600秒）であること
        assert len(sessions) == 2
        # 第1セッション: 10:00 - 10:10 (600s)
        assert sessions[0][2] == 600.0
        # 第2セッション: 10:15 - 10:25 (600s)
        assert sessions[1][2] == 600.0


def test_lock_sleep_disconnect_excluded():
    """ロック・スリープ・切断の時間も同様に含まれない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)

        # 10:00 - 10:05: Excel
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="Excel.exe"))
        recorder.observe(WindowObservation(timestamp=t1, app_name="Excel.exe"))

        # 10:05 - 10:15: ロック
        recorder.observe(LockObservation(timestamp=t1, is_locked=True))
        t_unlock = datetime(2026, 9, 27, 10, 15, 0, tzinfo=timezone.utc)
        recorder.observe(LockObservation(timestamp=t_unlock, is_locked=False))

        # 10:15 - 10:20: Excel 再開
        t2 = datetime(2026, 9, 27, 10, 20, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t_unlock, app_name="Excel.exe"))
        recorder.observe(WindowObservation(timestamp=t2, app_name="Excel.exe"))

        # 10:20 - 10:40: スリープ
        recorder.observe(SleepObservation(timestamp=t2, is_asleep=True))
        t_wake = datetime(2026, 9, 27, 10, 40, 0, tzinfo=timezone.utc)
        recorder.observe(SleepObservation(timestamp=t_wake, is_asleep=False))

        # 10:40 - 10:50: Excel 再開
        t3 = datetime(2026, 9, 27, 10, 50, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t_wake, app_name="Excel.exe"))
        recorder.observe(WindowObservation(timestamp=t3, app_name="Excel.exe"))

        # 10:50 - 11:00: セッション切断
        recorder.observe(SessionDisconnectObservation(timestamp=t3, is_disconnected=True))
        t_reconnect = datetime(2026, 9, 27, 11, 0, 0, tzinfo=timezone.utc)
        recorder.observe(SessionDisconnectObservation(timestamp=t_reconnect, is_disconnected=False))

        # 11:00 - 11:05: Excel 再開
        t4 = datetime(2026, 9, 27, 11, 5, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t_reconnect, app_name="Excel.exe"))
        recorder.observe(WindowObservation(timestamp=t4, app_name="Excel.exe"))

        export_path = os.path.join(tmpdir, "export.zip")
        password = "test-password"
        recorder.export(
            time_range=TimeRange(start=t0, end=t4),
            password=password,
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT duration_seconds FROM app_sessions ORDER BY start_time ASC"
        )
        sessions = [row[0] for row in cursor.fetchall()]
        conn.close()

        # 4つのセッションに分かれ、ロック(10m)、スリープ(20m)、切断(10m)の時間は含まれない
        assert len(sessions) == 4
        assert sessions[0] == 300.0  # 5 min
        assert sessions[1] == 300.0  # 5 min
        assert sessions[2] == 600.0  # 10 min
        assert sessions[3] == 300.0  # 5 min


def test_idle_threshold_config():
    """idle とみなすまでの時間は設定値で、初期値を持つ"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        assert recorder.idle_threshold_seconds == 300.0  # default 5 minutes
        recorder.set_idle_threshold_seconds(180.0)
        assert recorder.idle_threshold_seconds == 180.0
