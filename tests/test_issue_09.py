import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    ClipboardObservation,
    OperationTypeObservation,
    TimeRange,
    WindowObservation,
)


def test_clipboard_content_never_saved_or_exported():
    """中身を含む偽の Copy 観測を流しても、書き出したファイル全体を検索して中身が見つからない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="Chrome.exe"))

        secret_text = "SuperSecretConfidentialClipboardData987654"
        recorder.observe(
            ClipboardObservation(
                timestamp=t1,
                action="copy",
                data_type="text",
                data_length=len(secret_text),
                raw_content=secret_text,
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


def test_chrome_copy_to_excel_paste():
    """Chrome で Copy → Excel で Paste が、元 Chrome・先 Excel の1件として残る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 2, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 3, 0, tzinfo=timezone.utc)

        recorder.observe(WindowObservation(timestamp=t0, app_name="Chrome.exe"))
        recorder.observe(
            ClipboardObservation(
                timestamp=t1,
                action="copy",
                data_type="text",
                data_length=120,
            )
        )

        recorder.observe(WindowObservation(timestamp=t2, app_name="Excel.exe"))
        recorder.observe(
            ClipboardObservation(
                timestamp=t3,
                action="paste",
                data_type="text",
                data_length=120,
            )
        )

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
            "SELECT source_app, target_app, data_type, data_length FROM clipboard_transfers"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Chrome.exe"
        assert row[1] == "Excel.exe"
        assert row[2] == "text"
        assert row[3] == 120


def test_paste_inferred_from_ctrl_v():
    """Paste の観測が無く Ctrl+V だけがある場合も組が作られる"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 2, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 27, 10, 3, 0, tzinfo=timezone.utc)

        # Chrome で Copy
        recorder.observe(WindowObservation(timestamp=t0, app_name="Chrome.exe"))
        recorder.observe(
            ClipboardObservation(timestamp=t1, action="copy", data_type="text", data_length=45)
        )

        # Excel に切り替えて Ctrl+V
        recorder.observe(WindowObservation(timestamp=t2, app_name="Excel.exe"))
        recorder.observe(
            OperationTypeObservation(timestamp=t3, operation_type="ctrl+v")
        )

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
            "SELECT source_app, target_app, data_type, data_length FROM clipboard_transfers"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Chrome.exe"
        assert row[1] == "Excel.exe"
        assert row[2] == "text"
        assert row[3] == 45


def test_copy_without_paste_recorded_with_empty_target():
    """対応する Paste が無い Copy も記録される（先のアプリは空）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)

        recorder.observe(WindowObservation(timestamp=t0, app_name="Notepad.exe"))
        recorder.observe(
            ClipboardObservation(timestamp=t1, action="copy", data_type="text", data_length=80)
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
            "SELECT source_app, target_app, data_type, data_length FROM clipboard_transfers"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Notepad.exe"
        assert row[1] == ""  # 先のアプリは空
        assert row[2] == "text"
        assert row[3] == 80
