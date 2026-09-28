"""#34 Analyst side: an export in, an Analysis Summary out.

Exports are made by the real Collector (Recorder), then handed to the analyst's
command-line entry, exactly as a consultant would.
"""

from __future__ import annotations

import json
import re
import socket
from datetime import timedelta

import pytest
import pyzipper
from conftest import PASSWORD, T0, use

from flowlens.analyst import main
from flowlens.core import TimeRange


def make_export(recorder, tmp_path, name="export.zip", password=PASSWORD):
    recorder.flush()
    dest = tmp_path / "exports" / name
    recorder.export(TimeRange(T0 - timedelta(days=60), T0 + timedelta(days=60)), password, dest)
    return dest


def analyze(tmp_path, *exports, passwords=None, extra=()):
    out = tmp_path / "analysis"
    answers = iter(passwords or [PASSWORD] * len(exports))
    code = main(
        [*map(str, exports), "--out", str(out), *extra], ask_password=lambda _: next(answers)
    )
    return code, out


def summary(out):
    return json.loads((out / "analysis_summary.json").read_text(encoding="utf-8"))


def test_app_time_from_live_capture(recorder, tmp_path):
    use(recorder, "excel.exe", 0, 30, title="売上.xlsx - Excel")
    use(recorder, "chrome.exe", 31, 40)
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))

    assert code == 0
    apps = {a["app"]: a["seconds"] for a in summary(out)["live"]["app_time"]}
    assert apps["excel.exe"] == pytest.approx(31 * 60, abs=60)
    assert apps["chrome.exe"] == pytest.approx(10 * 60, abs=60)
    assert list(apps) == ["excel.exe", "chrome.exe"]  # longest first


def test_basis_describes_what_was_analysed(recorder, tmp_path):
    use(recorder, "excel.exe", 0, 30)
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))

    basis = summary(out)["basis"]
    assert basis["files"] == 1
    assert basis["people"] == 1
    assert basis["live_days"] == 1
    assert basis["record_counts"]["app_sessions"] >= 1
    assert "removed_on_export" in basis
    assert any("日分" in note for note in basis["notes"])  # little data: said so


def test_summary_holds_no_rows_device_id_or_symbols(recorder, tmp_path):
    use(recorder, "excel.exe", 0, 30, title="顧客A 請求書.xlsx - Excel")
    export = make_export(recorder, tmp_path)
    with pyzipper.AESZipFile(export) as zf:
        zf.setpassword(PASSWORD.encode())
        device_id = json.loads(zf.read("manifest.json"))["device_id"]
    code, out = analyze(tmp_path, export)

    text = (out / "analysis_summary.json").read_text(encoding="utf-8")
    assert device_id not in text
    assert "顧客A" not in text
    assert not re.search(r"\b[0-9a-f]{16}\b", text)


@pytest.mark.parametrize(
    "setup, reason",
    [
        ("wrong_password", "パスワード"),
        ("not_a_zip", "壊れて"),
        ("not_flowlens", "FlowLens の書き出しではありません"),
        ("unknown_version", "版"),
    ],
)
def test_unreadable_files_stop_with_a_reason(recorder, tmp_path, capsys, setup, reason):
    use(recorder, "excel.exe", 0, 5)
    export = make_export(recorder, tmp_path)
    passwords = [PASSWORD]
    if setup == "wrong_password":
        passwords = ["wrong"]
    elif setup == "not_a_zip":
        export.write_bytes(b"not a zip at all")
    elif setup == "not_flowlens":
        export = tmp_path / "other.zip"
        with pyzipper.AESZipFile(export, "w", encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(PASSWORD.encode())
            zf.writestr("hello.txt", "hi")
    elif setup == "unknown_version":
        with pyzipper.AESZipFile(export) as zf:
            zf.setpassword(PASSWORD.encode())
            members = {n: zf.read(n) for n in zf.namelist()}
        manifest = json.loads(members["manifest.json"])
        manifest["schema_version"] = 999
        members["manifest.json"] = json.dumps(manifest).encode()
        with pyzipper.AESZipFile(export, "w", encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(PASSWORD.encode())
            for n, data in members.items():
                zf.writestr(n, data)

    code, out = analyze(tmp_path, export, passwords=passwords)

    assert code != 0
    err = capsys.readouterr().err
    assert export.name in err and reason in err
    assert not (out / "analysis_summary.json").exists()


def test_no_decrypted_files_are_left_behind(recorder, tmp_path, monkeypatch):
    work = tmp_path / "tmp"
    work.mkdir()
    monkeypatch.setenv("TMPDIR", str(work))
    monkeypatch.setenv("TEMP", str(work))
    monkeypatch.setenv("TMP", str(work))
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", None)
    use(recorder, "excel.exe", 0, 5)
    analyze(tmp_path, make_export(recorder, tmp_path))
    assert list(work.iterdir()) == []


def test_password_from_environment(recorder, tmp_path, monkeypatch):
    use(recorder, "excel.exe", 0, 5)
    export = make_export(recorder, tmp_path)
    monkeypatch.setenv("FLOWLENS_PASSWORD", PASSWORD)

    def never(_):
        raise AssertionError("should not ask")

    out = tmp_path / "analysis"
    assert main([str(export), "--out", str(out)], ask_password=never) == 0


def test_no_network_is_used(recorder, tmp_path, monkeypatch):
    use(recorder, "excel.exe", 0, 5)
    export = make_export(recorder, tmp_path)

    def refuse(*args, **kwargs):
        raise AssertionError("network used")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert analyze(tmp_path, export)[0] == 0
