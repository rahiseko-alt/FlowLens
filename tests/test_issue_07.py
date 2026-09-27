import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import TimeRange, WindowObservation


def test_window_title_redacted_and_hashed():
    """題名の生の文字列は保存も書き出しもされない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)

        sensitive_title = "○○商事_見積.xlsx - Excel"
        recorder.observe(
            WindowObservation(timestamp=t0, app_name="Excel.exe", window_title=sensitive_title)
        )
        recorder.observe(
            WindowObservation(timestamp=t1, app_name="Excel.exe", window_title=sensitive_title)
        )

        export_path = os.path.join(tmpdir, "export.zip")
        password = "test-password"
        recorder.export(
            time_range=TimeRange(start=t0, end=t1),
            password=password,
            destination=export_path,
        )

        # ZIPバイナリ自体を検索
        with open(export_path, "rb") as f:
            raw_zip = f.read()
        assert "○○商事".encode("utf-8") not in raw_zip
        assert "見積".encode("utf-8") not in raw_zip

        # 展開して中のファイルも全て検索
        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.extractall(path=tmpdir, members=["data.sqlite", "manifest.json"])

        with open(os.path.join(tmpdir, "manifest.json"), "rb") as f:
            manifest_bytes = f.read()
        assert "○○商事".encode("utf-8") not in manifest_bytes
        assert "見積".encode("utf-8") not in manifest_bytes

        with open(os.path.join(tmpdir, "data.sqlite"), "rb") as f:
            sqlite_bytes = f.read()
        assert "○○商事".encode("utf-8") not in sqlite_bytes
        assert "見積".encode("utf-8") not in sqlite_bytes


def test_same_title_same_hash_different_title_different_hash():
    """同じ題名は同じ記号、違う題名は違う記号になる"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 10, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 15, 0, tzinfo=timezone.utc)
        t4 = datetime(2026, 9, 27, 10, 20, 0, tzinfo=timezone.utc)

        # Title A
        recorder.observe(
            WindowObservation(timestamp=t0, app_name="Excel.exe", window_title="Report_A.xlsx")
        )
        recorder.observe(
            WindowObservation(timestamp=t1, app_name="Word.exe", window_title="Document_B.docx")
        )
        recorder.observe(
            WindowObservation(timestamp=t2, app_name="Excel.exe", window_title="Report_A.xlsx")
        )
        recorder.observe(
            WindowObservation(timestamp=t3, app_name="Excel.exe", window_title="Report_C.xlsx")
        )
        recorder.observe(
            WindowObservation(timestamp=t4, app_name="Excel.exe", window_title="Report_C.xlsx")
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t4),
            password="test-password",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"test-password")
            zf.extractall(path=tmpdir, members=["data.sqlite"])

        conn = sqlite3.connect(os.path.join(tmpdir, "data.sqlite"))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT app_name, window_title_hash, window_title_ext "
            "FROM app_sessions ORDER BY start_time ASC"
        )
        rows = cursor.fetchall()
        conn.close()

        assert rows[0][1] == rows[2][1]  # Same title has same hash
        assert rows[0][1] != rows[1][1]  # Different title has different hash
        assert rows[0][1] != rows[3][1]  # Different title has different hash


def test_extension_extracted_separately():
    """拡張子（例: .xlsx）が読み取れる場合は別の項目として残る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        recorder.observe(
            WindowObservation(
                timestamp=t0,
                app_name="Excel.exe",
                window_title="Project_Plan.xlsx - Excel",
            )
        )
        recorder.observe(
            WindowObservation(
                timestamp=t1,
                app_name="Excel.exe",
                window_title="Project_Plan.xlsx - Excel",
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
        cursor.execute("SELECT window_title_ext FROM app_sessions")
        ext = cursor.fetchone()[0]
        conn.close()

        assert ext == ".xlsx"


def test_key_not_in_export_and_persisted():
    """鍵は書き出したファイルに含まれず、PC内で一度作られ再起動しても変わらない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder1 = Recorder(storage_dir=tmpdir)
        key1 = recorder1.key_manager.get_key()

        # Check key persistence
        recorder2 = Recorder(storage_dir=tmpdir)
        key2 = recorder2.key_manager.get_key()
        assert key1 == key2

        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 5, 0, tzinfo=timezone.utc)
        recorder1.observe(
            WindowObservation(timestamp=t0, app_name="App.exe", window_title="Secret Title")
        )
        recorder1.observe(
            WindowObservation(timestamp=t1, app_name="App.exe", window_title="Secret Title")
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder1.export(
            time_range=TimeRange(start=t0, end=t1),
            password="pwd",
            destination=export_path,
        )

        with pyzipper.AESZipFile(export_path) as zf:
            namelist = zf.namelist()
            assert "secret.key" not in namelist
            assert "key" not in namelist
            zf.setpassword(b"pwd")
            for name in namelist:
                content = zf.read(name)
                assert key1 not in content
