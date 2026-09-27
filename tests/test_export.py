"""#5 the minimal path: observations in, one encrypted Diagnostic Export out."""

import getpass
import socket
from datetime import timedelta

import pytest
import pyzipper
from conftest import PASSWORD, T0, at, open_export, use

from flowlens.core import TimeRange, WindowObservation


def switch(recorder, minute, app, title=""):
    recorder.observe(WindowObservation(timestamp=at(minute), app_name=app, window_title=title))


def test_app_sessions_in_order_with_durations(recorder, export):
    switch(recorder, 0, "chrome.exe")
    switch(recorder, 2, "EXCEL.EXE")
    switch(recorder, 7, "OUTLOOK.EXE")
    switch(recorder, 8, "OUTLOOK.EXE")

    rows = export().rows(
        "SELECT app_name, duration_seconds, is_past FROM app_sessions ORDER BY start_time"
    )

    assert rows == [
        {"app_name": "chrome.exe", "duration_seconds": 120.0, "is_past": 0},
        {"app_name": "excel.exe", "duration_seconds": 300.0, "is_past": 0},
        {"app_name": "outlook.exe", "duration_seconds": 60.0, "is_past": 0},
    ]


def test_export_is_aes256_and_needs_the_password(recorder, export, tmp_path):
    switch(recorder, 0, "chrome.exe")
    switch(recorder, 1, "excel.exe")
    exp = export()

    with pyzipper.AESZipFile(exp.path) as zf:
        for info in zf.infolist():
            assert info.flag_bits & 0x1, f"{info.filename} is not encrypted"
        zf.setpassword(PASSWORD.encode())
        zf.read("manifest.json")
    # WinZip AES extra field (0x9901): vendor "AE", strength byte 3 = AES-256
    raw = exp.path.read_bytes()
    header = raw.index(b"PK\x03\x04")
    extra = raw[header : header + 200]
    aes = extra.index(b"\x01\x99")
    assert extra[aes + 6 : aes + 8] == b"AE"
    assert extra[aes + 8] == 3
    with pytest.raises(RuntimeError):
        open_export(exp.path, tmp_path, password="wrong")


def test_manifest_fields_and_no_machine_identity(recorder, export):
    switch(recorder, 0, "chrome.exe")
    switch(recorder, 1, "excel.exe")
    exp = export()
    manifest = exp.json("manifest.json")

    for key in (
        "schema_version",
        "application_version",
        "export_created_at",
        "period_start",
        "period_end",
        "device_id",
        "record_counts",
    ):
        assert key in manifest
    assert manifest["record_counts"]["app_sessions"] == 1
    assert len(manifest["device_id"]) == 36
    assert not exp.contains(socket.gethostname())
    assert not exp.contains(getpass.getuser())
    assert set(exp.members) == {
        "data.sqlite",
        "manifest.json",
        "summary.json",
        "redaction_report.json",
        "README.txt",
    }


def test_records_outside_the_period_are_left_out_and_edges_trimmed(recorder, export):
    use(recorder, "chrome.exe", 0, 59)
    use(recorder, "excel.exe", 60, 119)  # chrome 0..60, excel 60..120
    switch(recorder, 120, "outlook.exe")

    exp = export(TimeRange(at(30), at(90)))
    rows = exp.rows("SELECT app_name, start_time, duration_seconds FROM app_sessions")

    assert [(r["app_name"], r["duration_seconds"]) for r in rows] == [
        ("chrome.exe", 1800.0),
        ("excel.exe", 1800.0),
    ]
    assert exp.json("manifest.json")["record_counts"]["app_sessions"] == 2


def test_empty_password_is_refused_without_leaving_a_file(recorder, tmp_path):
    switch(recorder, 0, "chrome.exe")
    dest = tmp_path / "out" / "x.zip"
    with pytest.raises(ValueError):
        recorder.export(TimeRange(T0, T0 + timedelta(hours=1)), "", dest)
    assert not dest.exists()
    assert not list(dest.parent.glob("*")) if dest.parent.exists() else True


def test_no_plain_copy_is_left_behind(recorder, export, tmp_path):
    switch(recorder, 0, "chrome.exe")
    switch(recorder, 1, "excel.exe")
    export()
    leftovers = [p.name for p in (tmp_path / "data").rglob("*.sqlite")]
    assert leftovers == []
