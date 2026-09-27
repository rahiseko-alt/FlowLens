"""#7-#10: titles, typing, clipboard, UI elements and domains never reveal content."""

from conftest import at

from flowlens.core import (
    ClipboardObservation,
    ControlMetadataObservation,
    OperationTypeObservation,
    Recorder,
    TypingObservation,
    WindowObservation,
)

SECRET_TITLE = "○○商事_見積.xlsx - Excel"


def window(recorder, minute, app="excel.exe", title=SECRET_TITLE):
    recorder.observe(WindowObservation(timestamp=at(minute), app_name=app, window_title=title))


# ------------------------------------------------------------------ #7 titles


def test_titles_become_symbols_with_the_extension(recorder, export):
    window(recorder, 0)
    window(recorder, 1, title="Book2.xlsx - Excel")
    window(recorder, 2, title=SECRET_TITLE)
    window(recorder, 3, app="outlook.exe")
    exp = export()

    rows = exp.rows("SELECT title_symbol, title_ext FROM app_sessions ORDER BY start_time")
    assert [r["title_ext"] for r in rows] == [".xlsx", ".xlsx", ".xlsx"]
    assert rows[0]["title_symbol"] == rows[2]["title_symbol"] != rows[1]["title_symbol"]
    assert len(rows[0]["title_symbol"]) == 16
    for text in ("○○商事", "見積", "Book2"):
        assert not exp.contains(text)


def test_non_file_titles_keep_no_extension(recorder, export):
    window(recorder, 0, app="outlook.exe", title="Re: call John.Smith - Outlook")
    window(recorder, 1, app="chrome.exe", title="v2.0 release notes - Google Chrome")
    window(recorder, 2, app="excel.exe")
    exp = export()

    exts = [r["title_ext"] for r in exp.rows("SELECT title_ext FROM app_sessions")]
    assert exts == ["", ""]
    assert not exp.contains("Smith")


def test_symbols_are_stable_across_restarts_and_the_key_is_not_exported(tmp_path, clock, export):
    first = Recorder(tmp_path / "data", clock=clock)
    window(first, 0)
    window(first, 1, app="outlook.exe")
    second = Recorder(tmp_path / "data", clock=clock)
    window(second, 2)
    window(second, 3, app="outlook.exe")
    exp = export()

    symbols = {
        r["title_symbol"]
        for r in exp.rows("SELECT title_symbol FROM app_sessions WHERE app_name='excel.exe'")
    }
    assert len(symbols) == 1
    key = (tmp_path / "data" / "secret.key").read_bytes()
    assert not any(key in blob for blob in exp.members.values())
    assert not exp.contains(key.hex())


def test_document_names_passed_as_app_names_are_not_kept(recorder, export):
    window(recorder, 0, app=r"C:\Users\yamada\給与明細_山田.xlsx", title="")
    window(recorder, 1, app="excel.exe")
    exp = export()

    assert not exp.contains("給与明細")
    assert not exp.contains("yamada")
    assert exp.rows("SELECT app_name FROM app_sessions")[0]["app_name"] == "other"


# ------------------------------------------------------------------ #8 typing


def test_typing_counts_without_characters(recorder, export):
    window(recorder, 0)
    recorder.observe(TypingObservation(timestamp=at(1), keystrokes=42, duration_seconds=30))
    recorder.observe(OperationTypeObservation(timestamp=at(2), operation_type="enter"))
    recorder.observe(OperationTypeObservation(timestamp=at(2), operation_type="Ctrl+S"))
    window(recorder, 3, app="outlook.exe")
    exp = export()

    typing = exp.rows("SELECT app_name, keystroke_count, duration_seconds FROM typing_activities")
    assert typing == [{"app_name": "excel.exe", "keystroke_count": 42, "duration_seconds": 30.0}]
    ops = exp.rows("SELECT app_name, operation_type FROM operation_events")
    assert ops == [{"app_name": "excel.exe", "operation_type": "enter"}]  # unknown ops dropped


def test_password_fields_leave_only_the_fact(recorder, export):
    window(recorder, 0)
    recorder.observe(
        TypingObservation(timestamp=at(1), keystrokes=12, duration_seconds=4, is_password=True)
    )
    exp = export()

    rows = exp.rows("SELECT keystroke_count, is_password FROM typing_activities")
    assert rows == [{"keystroke_count": 0, "is_password": 1}]
    assert exp.json("redaction_report.json")["password_field_typing_records"] == 1


# ------------------------------------------------------------------ #9 clipboard


def test_copy_paste_becomes_one_transfer_without_content(recorder, export):
    window(recorder, 0, app="chrome.exe")
    recorder.observe(ClipboardObservation(at(1), "copy", "text", 120, app_name="chrome.exe"))
    window(recorder, 2)
    recorder.observe(ClipboardObservation(at(3), "paste", app_name="excel.exe"))
    exp = export()

    rows = exp.rows(
        "SELECT action, source_app, target_app, data_type, data_length FROM clipboard_transfers"
    )
    assert rows == [
        {
            "action": "copy",
            "source_app": "chrome.exe",
            "target_app": "excel.exe",
            "data_type": "text",
            "data_length": 120,
        }
    ]
    assert exp.json("summary.json")["live"]["clipboard_transfers"] == {"chrome.exe->excel.exe": 1}


def test_ctrl_v_stands_in_for_an_undetected_paste(recorder, export):
    recorder.observe(ClipboardObservation(at(1), "cut", "files", 3, app_name="explorer.exe"))
    recorder.observe(OperationTypeObservation(at(2), "ctrl+v", app_name="outlook.exe"))
    exp = export()

    rows = exp.rows("SELECT action, source_app, target_app FROM clipboard_transfers")
    assert rows == [{"action": "cut", "source_app": "explorer.exe", "target_app": "outlook.exe"}]


def test_a_copy_without_paste_is_kept_with_no_target(recorder, export):
    recorder.observe(ClipboardObservation(at(1), "copy", app_name="chrome.exe"))
    recorder.observe(ClipboardObservation(at(2), "copy", app_name="excel.exe"))
    exp = export()

    targets = [r["target_app"] for r in exp.rows("SELECT target_app FROM clipboard_transfers")]
    assert targets == ["", ""]


# ------------------------------------------------------------------ #10 UI elements, domains


def test_control_metadata_and_domain_only(recorder, export):
    window(recorder, 0, app="chrome.exe", title="顧客A 様 - Google Chrome")
    recorder.observe(
        ControlMetadataObservation(
            timestamp=at(1),
            event_type="click",
            control_type="ButtonControl",
            automation_id="saveButton",
            class_name="Chrome_WidgetWin_1",
            framework_id="Chrome",
            browser_domain="https://crm.example.com/customer/123?token=abc#x",
            app_name="chrome.exe",
        )
    )
    exp = export()

    row = exp.rows("SELECT * FROM control_events")[0]
    assert row["control_type"] == "ButtonControl"
    assert row["automation_id"] == "saveButton"
    assert row["browser_domain"] == "crm.example.com"
    for text in ("customer/123", "token", "abc", "顧客A"):
        assert not exp.contains(text)


def test_content_looking_identifiers_and_bad_schemes_are_dropped(recorder, export):
    recorder.observe(
        ControlMetadataObservation(
            timestamp=at(1),
            automation_id="山田 太郎 様への返信",
            class_name="x y",
            browser_domain="file:///C:/Users/yamada/secret.txt",
            app_name="chrome.exe",
        )
    )
    exp = export()

    row = exp.rows("SELECT automation_id, class_name, browser_domain FROM control_events")[0]
    assert row == {"automation_id": "", "class_name": "", "browser_domain": ""}
    assert not exp.contains("山田")
    assert not exp.contains("secret")
