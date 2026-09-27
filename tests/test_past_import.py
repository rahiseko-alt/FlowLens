"""#14 Past Import: selected sources, sanitized, kept apart from live records."""

from datetime import timedelta

from conftest import T0, at, use

from flowlens.core import (
    PastAppStatsObservation,
    PastBrowserObservation,
    PastFileObservation,
    PastSystemEventObservation,
)


def providers():
    return {
        "system_log": lambda: [
            PastSystemEventObservation("boot", at(-600)),
            PastSystemEventObservation("sleep", at(-300)),
        ],
        "user_assist": lambda: [
            PastAppStatsObservation("EXCEL.EXE", at(-60), run_count=40, focus_seconds=9000),
            PastAppStatsObservation("給与明細_山田.xlsx", at(-60), run_count=3),
        ],
        "recent_files": lambda: [PastFileObservation("○○商事_請求書.xlsx", at(-120))],
        "browser_history": lambda: [
            PastBrowserObservation("crm.example.com", at(-30), app_name="chrome.exe"),
            PastBrowserObservation("https://x.example/p?q=secret", at(-30)),
            PastBrowserObservation("not a host", at(-30)),
        ],
    }


def test_past_records_are_sanitized_and_marked(recorder, export):
    report = recorder.import_past_providers(providers())
    exp = export()

    assert report["system_log"] == {"status": "success", "count": 2, "error": None}
    assert exp.rows("SELECT app_name, run_count, is_past FROM past_app_stats") == [
        {"app_name": "excel.exe", "run_count": 40, "is_past": 1}
    ]
    files = exp.rows("SELECT file_symbol, file_ext, is_past FROM file_events")
    assert files[0]["file_ext"] == ".xlsx" and len(files[0]["file_symbol"]) == 16
    assert sorted(r["domain"] for r in exp.rows("SELECT domain FROM browser_events")) == [
        "crm.example.com",
        "x.example",
    ]
    for text in ("給与明細", "山田", "○○商事", "請求書", "secret", "/p"):
        assert not exp.contains(text)


def test_past_and_live_are_kept_apart(recorder, export):
    recorder.import_past_providers(providers())
    use(recorder, "excel.exe", 0, 10)
    summary = export().json("summary.json")

    assert summary["live"]["apps"]["excel.exe"]["duration_seconds"] == 600.0
    assert summary["past"]["app_usage_counters"]["excel.exe"]["run_count"] == 40
    assert summary["past"]["system_events"] == {"boot": 1, "sleep": 1}


def test_only_selected_sources_are_read(recorder, export):
    read = []
    recorder.set_enabled_past_sources(["system_log"])
    report = recorder.import_past_providers(
        {
            "system_log": lambda: read.append("system_log") or [],
            "browser_history": lambda: read.append("browser_history") or [],
        }
    )
    assert read == ["system_log"]
    assert report["browser_history"]["status"] == "skipped"


def test_one_failing_source_does_not_stop_the_others(recorder, export):
    def broken():
        raise PermissionError(13, "Access is denied", r"C:\Users\yamada\AppData\SRUDB.dat")

    report = recorder.import_past_providers(
        {"security_log": broken, "system_log": providers()["system_log"]}
    )
    exp = export()

    assert report["security_log"]["status"] == "failed"
    assert report["security_log"]["error"] == "PermissionError 13"
    assert report["system_log"]["count"] == 2
    runs = exp.rows("SELECT source, status, error FROM past_import_runs ORDER BY source")
    assert runs == [
        {"source": "security_log", "status": "failed", "error": "PermissionError 13"},
        {"source": "system_log", "status": "success", "error": None},
    ]
    assert not exp.contains("yamada")


def test_reimport_adds_newly_selected_sources_without_duplicates(recorder, export):
    recorder.set_enabled_past_sources(["system_log"])
    recorder.import_past_providers(providers())
    recorder.set_enabled_past_sources(None)
    second = recorder.import_past_providers(providers())
    exp = export()

    assert second["system_log"]["count"] == 0  # already there
    assert second["browser_history"]["count"] == 2
    assert len(exp.rows("SELECT * FROM system_events")) == 2
    assert len(exp.rows("SELECT * FROM past_app_stats")) == 1


def test_records_older_than_30_days_are_not_imported(recorder, clock, export):
    clock.now = T0
    recorder.import_past_providers(
        {
            "system_log": lambda: [
                PastSystemEventObservation("boot", T0 - timedelta(days=31)),
                PastSystemEventObservation("boot", T0 - timedelta(days=29)),
            ]
        }
    )
    assert len(export().rows("SELECT * FROM system_events")) == 1
