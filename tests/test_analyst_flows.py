"""#38 Flow candidates: repeated sequences of apps in Live Capture.
#39 Transfer candidates, typing and operation keys.
"""

from __future__ import annotations

from datetime import timedelta

from analyst_support import run
from conftest import at, use

from flowlens.core import (
    ClipboardObservation,
    OperationTypeObservation,
    TypingObservation,
    WindowObservation,
)

DAY = 24 * 60  # minutes


def routine(recorder, day, steps=("outlook.exe", "chrome.exe", "excel.exe")):
    """One run of the routine on `day`: each app for 3 minutes, back to back."""
    base = day * DAY
    for i, app in enumerate(steps):
        use(recorder, app, base + i * 3, base + i * 3 + 2)


def flows(result):
    return [c for c in result["candidates"] if c["kind"] == "流れ"]


# ------------------------------------------------------------------ #38


def test_a_repeated_routine_is_a_flow_candidate(recorder, tmp_path):
    for day in range(3):
        routine(recorder, day)
    found = flows(run(recorder, tmp_path))

    assert [c["steps"] for c in found] == [["outlook.exe", "chrome.exe", "excel.exe"]]
    c = found[0]
    assert c["count"] == 3 and c["days"] == 3
    assert abs(c["minutes_per_time"] - 9) <= 1
    assert c["monthly_minutes_estimate"] == round(1 * c["minutes_per_time"] * 20)


def test_a_glimpse_in_between_does_not_break_the_flow(recorder, tmp_path):
    for day in range(3):
        use(recorder, "outlook.exe", day * DAY, day * DAY + 2)
        # a 2-second flash of another window between the two
        flash = at(day * DAY + 3) - timedelta(seconds=2)
        recorder.observe(WindowObservation(flash, "explorer.exe"))
        use(recorder, "excel.exe", day * DAY + 3, day * DAY + 5)
    found = flows(run(recorder, tmp_path))

    assert [c["steps"] for c in found] == [["outlook.exe", "excel.exe"]]


def test_a_break_splits_the_flow(recorder, tmp_path):
    for day in range(3):
        use(recorder, "outlook.exe", day * DAY, day * DAY + 2)
        use(recorder, "chrome.exe", day * DAY + 40, day * DAY + 42)  # away for 38 minutes
    assert flows(run(recorder, tmp_path)) == []


def test_a_shorter_flow_is_kept_only_when_it_happens_more_often(recorder, tmp_path):
    for day in range(3):
        routine(recorder, day)
    for day in range(3, 5):  # outlook -> chrome also happens on its own
        routine(recorder, day, steps=("outlook.exe", "chrome.exe"))
    found = {tuple(c["steps"]): c for c in flows(run(recorder, tmp_path))}

    assert set(found) == {
        ("outlook.exe", "chrome.exe", "excel.exe"),
        ("outlook.exe", "chrome.exe"),
    }
    assert found[("outlook.exe", "chrome.exe")]["count"] == 5
    assert found[("outlook.exe", "chrome.exe")]["contained_in"] == [
        ["outlook.exe", "chrome.exe", "excel.exe"]
    ]


# ------------------------------------------------------------------ #39


def transfer(recorder, minute, source="chrome.exe", target="excel.exe", title="台帳.xlsx"):
    use(recorder, source, minute, minute + 1)
    recorder.observe(ClipboardObservation(at(minute + 1), "copy", app_name=source))
    use(recorder, target, minute + 2, minute + 3, title=f"{title} - Excel")
    recorder.observe(ClipboardObservation(at(minute + 2.5), "paste", app_name=target))


def test_transfers_between_apps_are_counted(recorder, tmp_path):
    for day in range(3):
        transfer(recorder, day * DAY)
    transfer(recorder, 3 * DAY, target="notepad.exe", title="メモ")
    recorder.observe(ClipboardObservation(at(3 * DAY + 10), "copy", app_name="chrome.exe"))
    result = run(recorder, tmp_path)

    pairs = {(p["from"], p["to"]): p["count"] for p in result["live"]["transfers"]}
    assert pairs[("chrome.exe", "excel.exe")] == 3
    assert pairs[("chrome.exe", "notepad.exe")] == 1
    assert result["live"]["transfers_without_paste"] == 1


def test_repeated_transfers_into_the_same_screen_are_a_candidate(recorder, tmp_path):
    for day in range(3):
        transfer(recorder, day * DAY)
    found = [c for c in run(recorder, tmp_path)["candidates"] if c["kind"] == "転記"]

    assert len(found) == 1
    c = found[0]
    assert c["steps"] == ["chrome.exe", "excel.exe"]
    assert c["labels"] == ["ファイル A"]
    assert c["count"] == 3 and c["days"] == 3


def test_typing_and_keys_per_app_without_password_fields(recorder, tmp_path):
    use(recorder, "excel.exe", 0, 5)
    recorder.observe(
        TypingObservation(at(1), keystrokes=120, duration_seconds=60, app_name="excel.exe")
    )
    recorder.observe(
        TypingObservation(
            at(3), keystrokes=12, duration_seconds=5, is_password=True, app_name="excel.exe"
        )
    )
    for m in (1.5, 2, 2.5):
        recorder.observe(OperationTypeObservation(at(m), "enter", app_name="excel.exe"))
    recorder.observe(OperationTypeObservation(at(4), "tab", app_name="excel.exe"))
    live = run(recorder, tmp_path)["live"]

    typing = {t["app"]: t for t in live["typing"]}
    assert typing["excel.exe"]["keystrokes"] == 120
    assert typing["excel.exe"]["seconds"] == 60
    keys = {k["app"]: k["keys"] for k in live["operation_keys"]}
    assert keys["excel.exe"] == {"enter": 3, "tab": 1}
