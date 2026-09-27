"""#6 idle, lock, sleep and disconnect never count as work."""

import pytest
from conftest import at, use

from flowlens.core import (
    IdleObservation,
    LockObservation,
    SessionDisconnectObservation,
    SleepObservation,
    WindowObservation,
)


def window(recorder, minute, app="excel.exe"):
    recorder.observe(WindowObservation(timestamp=at(minute), app_name=app))


def durations(exp):
    return [
        (r["app_name"], r["duration_seconds"])
        for r in exp.rows("SELECT app_name, duration_seconds FROM app_sessions ORDER BY start_time")
    ]


def test_idle_ends_the_session_at_the_last_input(recorder, export):
    # The watcher keeps reporting the window every minute until it notices the idle
    # (5 minutes after the last input at minute 10), and then reports idle as starting
    # at the last input.
    for minute in range(0, 15):
        window(recorder, minute)
    recorder.observe(IdleObservation(timestamp=at(10), is_idle=True))
    recorder.observe(IdleObservation(timestamp=at(40), is_idle=False))
    use(recorder, "excel.exe", 40, 45)

    assert durations(export()) == [("excel.exe", 600.0), ("excel.exe", 300.0)]


@pytest.mark.parametrize(
    "away, back",
    [
        (LockObservation(timestamp=at(10), is_locked=True), LockObservation(at(40), False)),
        (SleepObservation(timestamp=at(10), is_asleep=True), SleepObservation(at(40), False)),
        (
            SessionDisconnectObservation(timestamp=at(10), is_disconnected=True),
            SessionDisconnectObservation(at(40), False),
        ),
    ],
)
def test_lock_sleep_disconnect_are_not_work(recorder, export, away, back):
    use(recorder, "excel.exe", 0, 5)
    recorder.observe(away)
    window(recorder, 20)  # ignored: nobody is there
    recorder.observe(back)
    use(recorder, "excel.exe", 40, 50)

    assert durations(export()) == [("excel.exe", 600.0), ("excel.exe", 600.0)]


def test_unlock_during_pause_is_not_missed(recorder, export):
    window(recorder, 0)
    recorder.observe(LockObservation(timestamp=at(5), is_locked=True))
    recorder.pause(at(6))
    recorder.observe(LockObservation(timestamp=at(7), is_locked=False))
    recorder.resume(at(8))
    use(recorder, "excel.exe", 10, 20)

    assert ("excel.exe", 600.0) in durations(export())


def test_silence_longer_than_the_threshold_is_not_work(recorder, export):
    window(recorder, 0)
    window(recorder, 1)
    window(recorder, 100)  # nothing observed for 99 minutes (e.g. an unnoticed sleep)
    window(recorder, 101)

    assert durations(export()) == [("excel.exe", 60.0), ("excel.exe", 60.0)]


def test_idle_threshold_is_a_setting(recorder, export):
    assert recorder.idle_threshold_seconds == 300
    recorder.set_idle_threshold_seconds(60)
    window(recorder, 0)
    window(recorder, 3)  # a 3-minute gap now exceeds the threshold

    assert durations(export()) == []
