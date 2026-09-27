import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pyzipper

from flowlens.core import Recorder
from flowlens.core.models import (
    ControlMetadataObservation,
    TimeRange,
    WindowObservation,
)


def test_name_and_value_never_saved_or_exported():
    """Name・Value に文字列を持つ偽の観測を流しても、ファイル全体を検索して見つからない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="App.exe"))

        secret_name = "ConfidentialCustomerAccountName99"
        secret_value = "SensitiveSSNOrCreditCardNumber12345"

        recorder.observe(
            ControlMetadataObservation(
                timestamp=t1,
                event_type="click",
                control_type="Button",
                automation_id="SubmitBtn",
                class_name="WPFButton",
                framework_id="WPF",
                state="Enabled",
                name=secret_name,
                value=secret_value,
            )
        )

        export_path = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=t0, end=t1),
            password="pwd",
            destination=export_path,
        )

        with open(export_path, "rb") as f:
            raw_zip = f.read()
        assert secret_name.encode("utf-8") not in raw_zip
        assert secret_value.encode("utf-8") not in raw_zip

        with pyzipper.AESZipFile(export_path) as zf:
            zf.setpassword(b"pwd")
            zf.extractall(path=tmpdir, members=["data.sqlite", "manifest.json"])

        with open(os.path.join(tmpdir, "data.sqlite"), "rb") as f:
            db_bytes = f.read()
        assert secret_name.encode("utf-8") not in db_bytes
        assert secret_value.encode("utf-8") not in db_bytes


def test_control_metadata_fields_preserved():
    """Control Metadata の各項目（ControlType、AutomationId、ClassName、FrameworkId、状態）が残る"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 2, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="Finance.exe"))

        recorder.observe(
            ControlMetadataObservation(
                timestamp=t1,
                event_type="focus",
                control_type="Edit",
                automation_id="txtAmount",
                class_name="TextBox",
                framework_id="WinForm",
                state="Focused",
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
            "SELECT app_name, event_type, control_type, automation_id, "
            "class_name, framework_id, state FROM control_events"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Finance.exe"
        assert row[1] == "focus"
        assert row[2] == "Edit"
        assert row[3] == "txtAmount"
        assert row[4] == "TextBox"
        assert row[5] == "WinForm"
        assert row[6] == "Focused"


def test_browser_url_domain_only_and_redaction():
    """URL の観測からドメインだけが残り、パス・クエリ・フラグメントは見つからない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="msedge.exe"))

        full_url = "https://example.com/customer/123?token=abc#x"
        recorder.observe(
            ControlMetadataObservation(
                timestamp=t1,
                event_type="navigate",
                url=full_url,
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
        cursor.execute("SELECT browser_domain FROM control_events")
        domain = cursor.fetchone()[0]
        conn.close()

        assert domain == "example.com"

        # 展開したDBとZIP全体でパス・クエリ・フラグメントが一切存在しないことを確認
        with open(os.path.join(tmpdir, "data.sqlite"), "rb") as f:
            content = f.read()
        assert b"/customer/123" not in content
        assert b"token=abc" not in content
        assert b"#x" not in content


def test_non_http_https_url_filtered_out():
    """http / https 以外のアドレスは残らない"""
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)
        t0 = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 27, 10, 1, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, 10, 2, 0, tzinfo=timezone.utc)
        recorder.observe(WindowObservation(timestamp=t0, app_name="chrome.exe"))

        recorder.observe(
            ControlMetadataObservation(
                timestamp=t1,
                event_type="navigate",
                url="file:///C:/Users/user/secret.pdf",
            )
        )
        recorder.observe(
            ControlMetadataObservation(
                timestamp=t2,
                event_type="navigate",
                url="javascript:alert(1)",
            )
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
        cursor.execute("SELECT browser_domain FROM control_events")
        domains = [row[0] for row in cursor.fetchall()]
        conn.close()

        for d in domains:
            assert d == ""
