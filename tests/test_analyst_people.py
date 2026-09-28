"""#40 Several people's exports analysed together, without comparing them."""

from __future__ import annotations

import json
from datetime import timedelta

import pyzipper
from analyst_support import analyze, summary
from conftest import PASSWORD, T0, Clock, use

from flowlens.core import Recorder, TimeRange

DAY = 24 * 60


def person(tmp_path, name, days=3):
    recorder = Recorder(tmp_path / name, clock=Clock())
    for day in range(days):
        use(recorder, "outlook.exe", day * DAY, day * DAY + 2)
        use(recorder, "excel.exe", day * DAY + 3, day * DAY + 5)
    recorder.flush()
    return recorder


def export(recorder, tmp_path, name, password=PASSWORD, start=None, end=None):
    dest = tmp_path / "exports" / name
    rng = TimeRange(start or T0 - timedelta(days=60), end or T0 + timedelta(days=60))
    recorder.export(rng, password, dest)
    return dest


def test_people_are_counted_not_compared(tmp_path):
    a, b = person(tmp_path, "a"), person(tmp_path, "b")
    files = [export(a, tmp_path, "a.zip", "pw-a"), export(b, tmp_path, "b.zip", "pw-b")]
    code, out = analyze(tmp_path, *files, passwords=["pw-a", "pw-b"])

    assert code == 0
    result = summary(out)
    assert result["basis"]["files"] == 2
    assert result["basis"]["people"] == 2
    flow = next(c for c in result["candidates"] if c["kind"] == "流れ")
    assert flow["count"] == 6 and flow["people"] == 2

    text = (out / "analysis_summary.json").read_text(encoding="utf-8")
    for exp in files:
        with pyzipper.AESZipFile(exp) as zf:
            zf.setpassword(("pw-a" if exp.name == "a.zip" else "pw-b").encode())
            assert json.loads(zf.read("manifest.json"))["device_id"] not in text


def test_overlapping_exports_of_one_person_are_not_counted_twice(tmp_path):
    a = person(tmp_path, "a")
    first = export(a, tmp_path, "first.zip")
    second = export(a, tmp_path, "second.zip")
    code, out = analyze(tmp_path, first, second)
    both = summary(out)
    code, out = analyze(tmp_path, first)
    one = summary(out)

    assert both["basis"]["people"] == 1
    assert both["live"]["app_time"] == one["live"]["app_time"]
    assert both["basis"]["record_counts"] == one["basis"]["record_counts"]
    assert [c["count"] for c in both["candidates"]] == [c["count"] for c in one["candidates"]]


def test_a_session_cut_by_two_periods_is_counted_once(tmp_path):
    a = Recorder(tmp_path / "a", clock=Clock())
    use(a, "excel.exe", 0, 30)
    a.flush()
    early = export(a, tmp_path, "early.zip", end=T0 + timedelta(minutes=20))
    late = export(a, tmp_path, "late.zip", start=T0 + timedelta(minutes=10))
    code, out = analyze(tmp_path, early, late)

    seconds = {x["app"]: x["seconds"] for x in summary(out)["live"]["app_time"]}["excel.exe"]
    assert abs(seconds - 30 * 60) <= 60


def test_one_unreadable_file_stops_everything(tmp_path, capsys):
    a, b = person(tmp_path, "a"), person(tmp_path, "b")
    files = [export(a, tmp_path, "a.zip", "pw-a"), export(b, tmp_path, "b.zip", "pw-b")]
    code, out = analyze(tmp_path, *files, passwords=["pw-a", "wrong"])

    assert code != 0
    assert "b.zip" in capsys.readouterr().err
    assert not (out / "analysis_summary.json").exists()
