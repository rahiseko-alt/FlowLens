"""#12 deletion by range and automatic retention."""

from datetime import timedelta

import pytest
from conftest import T0

from flowlens.core import PastBrowserObservation, TimeRange, WindowObservation


def session(recorder, start, minutes=10, app="excel.exe"):
    for minute in range(minutes + 1):
        recorder.observe(
            WindowObservation(timestamp=start + timedelta(minutes=minute), app_name=app)
        )
    recorder.flush()


def starts(exp):
    return [r["start_time"][:10] for r in exp.rows("SELECT start_time FROM app_sessions")]


def test_delete_a_range(recorder, export):
    session(recorder, T0)
    session(recorder, T0 + timedelta(days=2))
    recorder.delete(TimeRange(T0 + timedelta(days=1), T0 + timedelta(days=3)))
    assert starts(export()) == ["2026-09-01"]


@pytest.mark.parametrize("scope, left", [("last_7_days", 1), ("last_30_days", 0), ("all", 0)])
def test_delete_presets(recorder, clock, export, scope, left):
    clock.now = T0 + timedelta(days=20)
    session(recorder, T0)  # 20 days ago
    session(recorder, T0 + timedelta(days=19, hours=12))  # yesterday
    recorder.delete(scope)
    assert len(starts(export())) == left


def test_delete_today_uses_the_local_calendar_day(recorder, clock, export, monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    import time

    time.tzset()
    try:
        clock.now = T0.replace(hour=3)  # 12:00 in Tokyo
        session(recorder, T0.replace(hour=0) - timedelta(hours=1))  # 08:00 Tokyo, today
        session(recorder, T0.replace(hour=0) - timedelta(hours=16))  # yesterday in Tokyo
        recorder.delete("today")
        assert starts(export()) == ["2026-08-31"]
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_retention_deletes_old_records_automatically(recorder, clock, export):
    clock.now = T0
    session(recorder, T0)
    recorder.import_past_providers(
        {"browser_history": lambda: [PastBrowserObservation("a.example", T0)]}
    )
    clock.now = T0 + timedelta(days=45)  # default retention is 30 days
    recorder.observe(WindowObservation(timestamp=clock.now, app_name="excel.exe"))

    exp = export(TimeRange(T0 - timedelta(days=1), clock.now))
    assert starts(exp) == []
    assert exp.rows("SELECT * FROM browser_events") == []


def test_unlimited_retention_keeps_everything(recorder, clock, export):
    recorder.set_retention_days(None)
    clock.now = T0
    session(recorder, T0)
    clock.now = T0 + timedelta(days=200)
    recorder.observe(WindowObservation(timestamp=clock.now, app_name="excel.exe"))
    assert starts(export(TimeRange(T0 - timedelta(days=1), clock.now))) == ["2026-09-01"]


def test_retention_choices(recorder):
    for days in (30, 60, 90, None):
        recorder.set_retention_days(days)
        assert recorder.get_retention_days() == days
    with pytest.raises(ValueError):
        recorder.set_retention_days(7)


def test_deleting_frees_space(recorder):
    for day in range(20):
        session(recorder, T0 - timedelta(days=day) + timedelta(days=4))
    before = recorder.get_status()["database_size_bytes"]
    recorder.delete("all")
    after = recorder.get_status()["database_size_bytes"]
    assert after <= before
    assert recorder.get_status()["session_count"] == 0
