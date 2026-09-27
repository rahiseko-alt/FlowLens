import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    OperationTypeObservation,
    TimeRange,
    TypingObservation,
    WindowObservation,
)


def test_raw_keystrokes_never_saved_or_exported():
    """文字を含む偽のキー入力を流しても、書き出したファイル全体を検索してその文字列が見つからない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="Word.exe"))

        secret_text = "ThisIsASecretConfidentialPassword123!"
        recorder.observe(
            TypingObservation(
                timestamp=t1,
                keystrokes=len(secret_text),
                duration_seconds=5.0,
                raw_text=secret_text,
            )
        )

        export_path = os.path.join(tmpdir, "export.zip")
        password = "test-password"
        recorder.export(
            time_range=TimeRange(start=t0, end=t1),
            password=password,
            destination=export_path,
        )

        # ZIP全体を検索
        with open(export_path, "rb") as f:
            raw_zip = f.read()
        assert secret_text.encode("utf-8") not in raw_zip

        # 展開して全ファイル検索
        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.extractall(path=tmpdir, members=["data.sqlite", "manifest.json"])

        with open(os.path.join(tmpdir, "manifest.json"), "rb") as f:
            assert secret_text.encode("utf-8") not in f.read()

        with open(os.path.join(tmpdir, "data.sqlite"), "rb") as f:
            assert secret_text.encode("utf-8") not in f.read()


def test_typing_activity_count_and_duration():
    """Typing Activity の回数と継続時間がウィンドウごとに正しい"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)

        # App 1: Word
        recorder.observe(
            WindowObservation(timestamp=t0, app_name="Word.exe", window_title="Doc1")
        )
        recorder.observe(
            TypingObservation(timestamp=t0, keystrokes=50, duration_seconds=30.0)
        )

        # App 2: Excel
        recorder.observe(
            WindowObservation(timestamp=t1, app_name="Excel.exe", window_title="Sheet1")
        )
        recorder.observe(
            TypingObservation(timestamp=t1, keystrokes=25, duration_seconds=15.0)
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t2),
            password="pwd",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT app_name, keystroke_count, duration_seconds "
            "FROM typing_activities ORDER BY start_time ASC"
        )
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] == "Word.exe"
        assert rows[0][1] == 50
        assert rows[0][2] == 30.0
        assert rows[1][0] == "Excel.exe"
        assert rows[1][1] == 25
        assert rows[1][2] == 15.0


def test_operation_type_saved_with_timestamp_and_app():
    """Operation Type が時刻・アプリつきで残る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 2, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 3, 0, tzinfo=timezone.utc)

        recorder.observe(WindowObservation(timestamp=t0, app_name="Editor.exe"))
        recorder.observe(OperationTypeObservation(timestamp=t1, operation_type="ctrl+c"))
        recorder.observe(OperationTypeObservation(timestamp=t2, operation_type="enter"))
        recorder.observe(OperationTypeObservation(timestamp=t3, operation_type="ctrl+v"))

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t3),
            password="pwd",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT app_name, operation_type, timestamp "
            "FROM operation_types ORDER BY timestamp ASC"
        )
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 3
        assert rows[0][0] == "Editor.exe"
        assert rows[0][1] == "ctrl+c"
        assert rows[1][1] == "enter"
        assert rows[2][1] == "ctrl+v"


def test_password_field_input_zero_count_duration_only():
    """パスワード欄での入力は回数も残らず、「パスワード欄の時間があった」ことだけが残る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 2, 0, tzinfo=timezone.utc)

        recorder.observe(WindowObservation(timestamp=t0, app_name="Browser.exe"))
        # Password field typing: 18 characters typed over 8.5 seconds
        recorder.observe(
            TypingObservation(
                timestamp=t1,
                keystrokes=18,
                duration_seconds=8.5,
                is_password=True,
                raw_text="SecretPassword999",
            )
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t1),
            password="pwd",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT app_name, keystroke_count, duration_seconds, is_password "
            "FROM typing_activities"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Browser.exe"
        assert row[1] == 0  # 回数は 0（残さない）
        assert row[2] == 8.5  # 時間だけが残る
        assert row[3] == 1  # パスワード欄フラグ
