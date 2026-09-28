"""Fixes from the review of the analyst command (PR #43)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pyzipper
from analyst_support import analyze, make_export, run, summary
from conftest import PASSWORD, T0, Clock, at, use

from flowlens.core import ClipboardObservation, PastFileObservation, Recorder

DAY = 24 * 60


def rewrite(export, change):
    """Re-packs an export after `change(members)` edits its files in place."""
    with pyzipper.AESZipFile(export) as zf:
        zf.setpassword(PASSWORD.encode())
        members = {n: zf.read(n) for n in zf.namelist()}
    change(members)
    with pyzipper.AESZipFile(export, "w", encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(PASSWORD.encode())
        for name, data in members.items():
            zf.writestr(name, data)


def test_estimate_is_per_recorded_day_not_per_day_seen(recorder, tmp_path):
    for day in range(10):
        if day in (0, 4, 8):
            use(recorder, "outlook.exe", day * DAY, day * DAY + 4)
            use(recorder, "excel.exe", day * DAY + 5, day * DAY + 9)
        use(recorder, "notepad.exe", day * DAY + 100, day * DAY + 110)  # recorded every day
    flow = next(c for c in run(recorder, tmp_path)["candidates"] if c["kind"] == "流れ")

    assert flow["monthly_minutes_estimate"] == round(3 / 10 * flow["minutes_per_time"] * 20)
    assert "10 日" in flow["formula"]


def test_the_label_table_is_outside_the_folder_given_to_the_ai(recorder, tmp_path):
    use(recorder, "excel.exe", 0, 20, title="月次報告.xlsx - Excel")
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))

    assert not any("labels" in p.name for p in out.rglob("*"))
    table = out.parent / f"{out.name}_do_not_send_to_ai" / "labels.json"
    assert "ファイル A" in json.loads(table.read_text(encoding="utf-8"))


def test_a_broken_database_inside_stops_with_a_reason(recorder, tmp_path, capsys):
    use(recorder, "excel.exe", 0, 5)
    export = make_export(recorder, tmp_path)
    rewrite(export, lambda m: m.update({"data.sqlite": b"not a database"}))
    code, out = analyze(tmp_path, export)

    assert code != 0
    err = capsys.readouterr().err
    assert export.name in err and "Traceback" not in err


def test_a_manifest_without_a_period_stops_with_a_reason(recorder, tmp_path, capsys):
    use(recorder, "excel.exe", 0, 5)
    export = make_export(recorder, tmp_path)

    def drop_period(members):
        manifest = json.loads(members["manifest.json"])
        del manifest["period_start"]
        members["manifest.json"] = json.dumps(manifest).encode()

    rewrite(export, drop_period)
    code, out = analyze(tmp_path, export)
    assert code != 0 and export.name in capsys.readouterr().err


def test_a_missing_file_is_named_before_asking_for_a_password(tmp_path, capsys):
    def never(_):
        raise AssertionError("should not ask")

    from flowlens.analyst import main

    code = main([str(tmp_path / "nothing.zip"), "--out", str(tmp_path / "a")], ask_password=never)
    assert code != 0
    assert "nothing.zip" in capsys.readouterr().err


def test_a_source_read_again_successfully_is_not_unreadable(recorder, tmp_path):
    def denied():
        raise PermissionError(13, "denied")

    recorder.import_past_providers({"recent_files": denied})
    recorder.import_past_providers({"recent_files": lambda: [PastFileObservation("a.xlsx", T0)]})
    assert run(recorder, tmp_path)["past"]["unreadable_sources"] == []


def test_admin_rights_are_named_only_for_permission_errors(recorder, tmp_path):
    def network():
        raise OSError(53, "network path not found")

    def denied():
        raise PermissionError(13, "denied")

    recorder.import_past_providers({"recent_files": network, "security_log": denied})
    reasons = {
        u["source"]: u["reason"] for u in run(recorder, tmp_path)["past"]["unreadable_sources"]
    }

    assert "管理者" not in reasons["recent_files"]
    assert "管理者" in reasons["security_log"]


def test_removals_are_not_counted_twice_for_one_person(recorder, tmp_path):
    recorder.add_excluded_app("keepass.exe")
    use(recorder, "keepass.exe", 0, 5)
    use(recorder, "excel.exe", 6, 10)
    export = make_export(recorder, tmp_path)
    code, out = analyze(tmp_path, export, export)
    twice = summary(out)["basis"]["removed_on_export"]
    code, out = analyze(tmp_path, export)
    assert twice == summary(out)["basis"]["removed_on_export"]


def test_hours_are_real_hours_across_a_clock_change(tmp_path):
    # London falls back at 01:00 UTC on 2026-10-25 (02:00 BST -> 01:00 GMT).
    start = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    recorder = Recorder(tmp_path / "ny", clock=Clock(start + timedelta(days=1)))
    from flowlens.core import WindowObservation

    for minute in range(61):
        recorder.observe(WindowObservation(start + timedelta(minutes=minute), "excel.exe"))
    grid = run(recorder, tmp_path, extra=["--tz", "Europe/London"])["live"]["weekday_hour"]

    assert abs(sum(sum(hours.values()) for hours in grid.values()) - 3600) <= 60


def test_instructions_say_contained_flows_are_not_added(recorder, tmp_path):
    use(recorder, "excel.exe", 0, 5)
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))
    assert "contained_in" in (out / "instructions_for_claude.md").read_text(encoding="utf-8")


def test_a_late_paste_does_not_count_as_long_transfer_work(recorder, tmp_path):
    for day in range(3):
        base = day * DAY
        use(recorder, "chrome.exe", base, base + 1)
        recorder.observe(ClipboardObservation(at(base + 1), "copy", app_name="chrome.exe"))
        use(recorder, "excel.exe", base + 2, base + 40, title="台帳.xlsx - Excel")
        recorder.observe(ClipboardObservation(at(base + 39), "paste", app_name="excel.exe"))
    found = next(c for c in run(recorder, tmp_path)["candidates"] if c["kind"] == "転記")

    assert found["minutes_per_time"] <= 5
