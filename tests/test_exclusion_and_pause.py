"""#11 excluded apps and pause leave only the fact that time passed."""

import pytest
from conftest import at, use

from flowlens.core import (
    ClipboardObservation,
    ControlMetadataObservation,
    PastBrowserObservation,
    PastFileObservation,
    Recorder,
    TypingObservation,
    WindowObservation,
)


def window(recorder, minute, app, title=""):
    recorder.observe(WindowObservation(timestamp=at(minute), app_name=app, window_title=title))


def test_excluded_app_leaves_only_excluded_time(recorder, export):
    recorder.add_excluded_app("KeePass.exe")
    use(recorder, "excel.exe", 0, 9)
    use(recorder, "keepass.exe", 10, 11, "銀行口座.kdbx - KeePass")
    recorder.observe(TypingObservation(at(11), keystrokes=30, app_name="keepass.exe"))
    recorder.observe(ClipboardObservation(at(12), "copy", app_name="keepass.exe"))
    recorder.observe(ControlMetadataObservation(at(12), app_name="keepass.exe"))
    use(recorder, "keepass.exe", 12, 19, "銀行口座.kdbx - KeePass")
    use(recorder, "excel.exe", 20, 21)
    exp = export()

    assert {r["app_name"] for r in exp.rows("SELECT app_name FROM app_sessions")} == {"excel.exe"}
    assert exp.rows("SELECT reason, duration_seconds FROM excluded_intervals") == [
        {"reason": "excluded_app", "duration_seconds": 600.0}
    ]
    for table in ("typing_activities", "clipboard_transfers", "control_events"):
        assert exp.rows(f"SELECT * FROM {table}") == []
    assert not exp.contains("keepass")
    assert not exp.contains("銀行口座")


def test_transfers_touching_an_excluded_app_are_dropped(recorder, export):
    recorder.add_excluded_app("keepass.exe")
    recorder.observe(ClipboardObservation(at(1), "copy", app_name="chrome.exe"))
    recorder.observe(ClipboardObservation(at(2), "paste", app_name="keepass.exe"))
    exp = export()
    assert exp.rows("SELECT * FROM clipboard_transfers") == []


def test_exclusion_added_after_recording_applies_to_export(recorder, export):
    use(recorder, "slack.exe", 0, 9)
    use(recorder, "excel.exe", 10, 11)
    recorder.add_excluded_app("slack.exe")
    exp = export()

    assert {r["app_name"] for r in exp.rows("SELECT app_name FROM app_sessions")} == {"excel.exe"}
    report = exp.json("redaction_report.json")
    assert report["excluded_app_records_by_table"] == {"app_sessions": 1}
    assert not exp.contains("slack")


def test_exclusion_applies_to_past_browser_history_and_files(recorder, export):
    recorder.add_excluded_app("chrome.exe")
    recorder.import_past_providers(
        {
            "browser_history": lambda: [
                PastBrowserObservation("bank.example.com", at(-60), app_name="chrome.exe"),
                PastBrowserObservation("news.example.com", at(-60), app_name="msedge.exe"),
            ],
            "recent_files": lambda: [
                PastFileObservation("a.xlsx", at(-60), app_name="chrome.exe"),
            ],
        }
    )
    exp = export()

    assert [r["domain"] for r in exp.rows("SELECT domain FROM browser_events")] == [
        "news.example.com"
    ]
    assert exp.rows("SELECT * FROM file_events") == []
    assert not exp.contains("bank.example.com")


def test_pause_records_nothing_but_the_pause(recorder, export):
    window(recorder, 0, "excel.exe")
    recorder.pause(at(5))
    window(recorder, 6, "chrome.exe")
    recorder.observe(TypingObservation(at(7), keystrokes=10))
    recorder.resume(at(15))
    window(recorder, 15, "excel.exe")
    window(recorder, 16, "excel.exe")
    exp = export()

    assert {r["app_name"] for r in exp.rows("SELECT app_name FROM app_sessions")} == {"excel.exe"}
    assert exp.rows("SELECT * FROM typing_activities") == []
    assert exp.rows("SELECT reason, duration_seconds FROM excluded_intervals") == [
        {"reason": "pause", "duration_seconds": 600.0}
    ]


def test_pause_survives_a_restart_and_blocks_past_import(tmp_path, clock):
    first = Recorder(tmp_path / "d", clock=clock)
    first.pause(at(0))
    second = Recorder(tmp_path / "d", clock=clock)
    assert second.is_paused
    report = second.import_past_providers(
        {"browser_history": lambda: [PastBrowserObservation("a.example.com", at(-5))]}
    )
    assert report["browser_history"]["status"] == "skipped"


def test_only_app_names_can_be_excluded(recorder):
    with pytest.raises(ValueError):
        recorder.add_excluded_app("給与明細.xlsx")
    recorder.add_excluded_app(r"C:\Program Files\Slack\Slack.exe")
    assert "slack.exe" in recorder.get_excluded_apps()
    recorder.remove_excluded_app("SLACK.EXE")
    assert "slack.exe" not in recorder.get_excluded_apps()


def test_password_managers_are_excluded_from_the_start(recorder):
    assert {"keepass.exe", "bitwarden.exe", "1password.exe"} <= set(recorder.get_excluded_apps())


def test_late_observations_stamped_inside_a_pause_are_dropped(recorder, export):
    # The input worker may hand over a typing burst or a copy after the pause ended.
    use(recorder, "excel.exe", 0, 1)
    recorder.pause(at(1))
    recorder.resume(at(10))
    recorder.observe(TypingObservation(at(5), keystrokes=300, app_name="excel.exe"))
    recorder.observe(TypingObservation(at(0.5), keystrokes=9, duration_seconds=60))  # spans it
    recorder.observe(ClipboardObservation(at(6), "copy", app_name="excel.exe"))
    use(recorder, "excel.exe", 10, 12)
    exp = export()

    assert exp.rows("SELECT * FROM typing_activities") == []
    assert exp.rows("SELECT * FROM clipboard_transfers") == []


def test_late_observations_stamped_inside_a_lock_are_dropped(recorder, export):
    from flowlens.core import LockObservation

    use(recorder, "excel.exe", 0, 1)
    recorder.observe(LockObservation(at(2), True))
    recorder.observe(LockObservation(at(10), False))
    recorder.observe(TypingObservation(at(5), keystrokes=30, app_name="excel.exe"))
    exp = export()
    assert exp.rows("SELECT * FROM typing_activities") == []
