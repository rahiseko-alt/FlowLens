import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pyzipper

from flowlens.core.models import (
    ClipboardObservation,
    PastAppUsageObservation,
    PastBrowserObservation,
    PastFileObservation,
    PastSystemEventObservation,
    TimeRange,
    WindowObservation,
)
from flowlens.core.recorder import Recorder


def test_consultant_export_unpacking_and_query_workflow():
    """偽の観測から作った書き出しファイルを展開し、手順書通りの問い合わせができる"""
    with tempfile.TemporaryDirectory() as tmpdir:
        now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        recorder = Recorder(storage_dir=tmpdir, clock=lambda: now)

        # 1. Simulate Live observations (fine-grained)
        t_live = now - timedelta(days=2)
        # Excel session with copy
        recorder.observe(
            WindowObservation(
                app_name="Excel.exe",
                window_title="WeeklyReport.xlsx",
                timestamp=t_live,
            )
        )
        recorder.observe(
            ClipboardObservation(
                action="copy",
                data_type="text",
                data_length=42,
                timestamp=t_live + timedelta(minutes=5),
            )
        )
        # Switch to Chrome and paste
        recorder.observe(
            WindowObservation(
                app_name="chrome.exe",
                window_title="Salesforce - Dashboard",
                timestamp=t_live + timedelta(minutes=6),
            )
        )
        recorder.observe(
            ClipboardObservation(
                action="paste",
                data_type="text",
                data_length=42,
                timestamp=t_live + timedelta(minutes=7),
            )
        )
        recorder.flush()

        # 2. Simulate Past observations (coarse)
        t_past = now - timedelta(days=15)
        recorder.import_past_records(
            "srum",
            [
                PastAppUsageObservation(
                    app_name="Excel.exe",
                    window_title="OldBudget.xlsx",
                    start_time=t_past,
                    end_time=t_past + timedelta(hours=1),
                    duration_seconds=3600.0,
                    source="srum",
                )
            ],
        )
        recorder.import_past_records(
            "recent_files",
            [
                PastFileObservation(
                    file_path=r"C:\Docs\Strategy.docx",
                    app_name="WINWORD.EXE",
                    timestamp=t_past + timedelta(days=1),
                    source="recent_files",
                )
            ],
        )
        recorder.import_past_records(
            "browser_history",
            [
                PastBrowserObservation(
                    url="https://portal.example.com/reports?tab=1",
                    timestamp=t_past + timedelta(days=2),
                    source="browser_history",
                )
            ],
        )
        recorder.import_past_records(
            "system_log",
            [
                PastSystemEventObservation(
                    event_type="boot",
                    timestamp=t_past - timedelta(days=1),
                    source="system_log",
                )
            ],
        )

        # 3. Export archive
        export_zip = os.path.join(tmpdir, "diagnostic_export.zip")
        recorder.export(
            time_range=TimeRange(start=now - timedelta(days=30), end=now),
            password="consultant_secure_pwd",
            destination=export_zip,
        )

        assert os.path.exists(export_zip)

        # 4. Unpack with password (simulating 7-Zip extraction)
        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with pyzipper.AESZipFile(export_zip) as zf:
            zf.setpassword(b"consultant_secure_pwd")
            zf.extractall(extract_dir)

        # Check expected files in archive per consultant guide
        extracted_files = set(os.listdir(extract_dir))
        assert "data.sqlite" in extracted_files
        assert "manifest.json" in extracted_files
        assert "summary.json" in extracted_files
        assert "redaction_report.json" in extracted_files
        assert "README.txt" in extracted_files

        # 5. Step 1 of Guide: Read summary.json
        with open(os.path.join(extract_dir, "summary.json"), encoding="utf-8") as f:
            summary = json.load(f)

        assert "live" in summary
        assert "past" in summary
        assert "transfers" in summary["live"]
        assert "Excel.exe" in summary["live"]["apps"]
        assert summary["live"]["apps"]["Excel.exe"]["duration_seconds"] > 0
        assert summary["past"]["apps"]["Excel.exe"]["duration_seconds"] == 3600.0

        # 6. Step 2 of Guide: Execute Query 1 & 2 on data.sqlite
        conn = sqlite3.connect(os.path.join(extract_dir, "data.sqlite"))
        conn.row_factory = sqlite3.Row

        # Query 1: Top apps grouped by is_past
        cur = conn.cursor()
        cur.execute(
            """
            SELECT app_name, is_past, SUM(duration_seconds) as total_duration
            FROM app_sessions
            GROUP BY app_name, is_past
            ORDER BY total_duration DESC
            """
        )
        app_rows = cur.fetchall()
        assert len(app_rows) >= 2

        # Query 2: Frequent app transition pairs in clipboard transfers
        cur.execute(
            """
            SELECT source_app, target_app, COUNT(*) as transfer_count
            FROM clipboard_transfers
            WHERE is_past = 0
            GROUP BY source_app, target_app
            ORDER BY transfer_count DESC
            """
        )
        transfer_rows = cur.fetchall()
        assert len(transfer_rows) == 1
        assert transfer_rows[0]["source_app"] == "Excel.exe"
        assert transfer_rows[0]["target_app"] == "chrome.exe"
        assert transfer_rows[0]["transfer_count"] == 1

        # Query 3: Repeated file extension usage
        cur.execute(
            """
            SELECT app_name, file_ext, COUNT(*) as cnt
            FROM file_events
            GROUP BY app_name, file_ext
            """
        )
        file_rows = cur.fetchall()
        assert len(file_rows) == 1
        assert file_rows[0]["file_ext"] == ".docx"

        # Query 4: Browser domain analysis
        cur.execute(
            """
            SELECT browser_domain, COUNT(*) as visits
            FROM browser_events
            GROUP BY browser_domain
            """
        )
        browser_rows = cur.fetchall()
        assert len(browser_rows) == 1
        assert browser_rows[0]["browser_domain"] == "portal.example.com"

        conn.close()
