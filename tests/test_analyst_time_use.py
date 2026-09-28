"""#35 Past Import's time use, and live weekday x hour in the customer's time zone.
#36 Symbols become labels; the label -> symbol table is kept apart from the summary.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from analyst_support import analyze, make_export, run, summary
from conftest import T0, use

from flowlens.core import PastAppStatsObservation, PastBrowserObservation, PastFileObservation


def past(recorder, **extra):
    day = timedelta(days=1)
    providers = {
        "user_assist": lambda: [
            PastAppStatsObservation("EXCEL.EXE", T0 - day, run_count=30, focus_seconds=6000),
            PastAppStatsObservation("chrome.exe", T0 - day, run_count=10, focus_seconds=4000),
        ],
        "recent_files": lambda: [
            PastFileObservation("月次報告.xlsx", T0 - 3 * day),
            PastFileObservation("月次報告.xlsx", T0 - 2 * day),
            PastFileObservation("見積.docx", T0 - 2 * day),
        ],
        "browser_history": lambda: [
            PastBrowserObservation("crm.example.com", T0 - 3 * day),
            PastBrowserObservation("crm.example.com", T0 - 3 * day + timedelta(hours=1)),
            PastBrowserObservation("crm.example.com", T0 - day),
        ],
        **extra,
    }
    recorder.import_past_providers(providers)


# ------------------------------------------------------------------ #35


def test_past_only_export_gives_a_summary(recorder, tmp_path):
    past(recorder)
    result = run(recorder, tmp_path)

    assert result["basis"]["live_days"] == 0
    assert result["live"]["app_time"] == []
    usage = {a["app"]: a for a in result["past"]["app_usage"]}
    assert usage["excel.exe"]["run_share"] == 0.75
    assert usage["excel.exe"]["focus_share"] == 0.6
    assert "run_count" not in usage["excel.exe"]  # lifetime counters: ratios only
    assert result["past"]["file_types"] == [
        {"ext": ".xlsx", "opens": 2},
        {"ext": ".docx", "opens": 1},
    ]
    assert result["past"]["sites"] == [{"domain": "crm.example.com", "days": 2}]


def test_past_and_live_do_not_mix(recorder, tmp_path):
    past(recorder)
    use(recorder, "notepad.exe", 0, 10)
    result = run(recorder, tmp_path)

    assert [a["app"] for a in result["live"]["app_time"]] == ["notepad.exe"]
    assert "notepad.exe" not in {a["app"] for a in result["past"]["app_usage"]}


def test_unreadable_past_sources_are_listed(recorder, tmp_path):
    def broken():
        raise PermissionError("denied")

    past(recorder, security_log=broken)
    failed = run(recorder, tmp_path)["past"]["unreadable_sources"]
    assert [f["source"] for f in failed] == ["security_log"]
    assert failed[0]["reason"]


def test_weekday_and_hour_in_japan_time(recorder, tmp_path):
    # T0 is Tuesday 09:00 UTC. 14:50-15:10 UTC is 23:50-00:10 in Tokyo, across midnight.
    use(recorder, "excel.exe", 350, 370)
    grid = run(recorder, tmp_path)["live"]["weekday_hour"]

    assert abs(grid["火"]["23"] - 600) <= 60
    assert abs(grid["水"]["0"] - 600) <= 60


def test_weekday_and_hour_follow_the_chosen_time_zone(recorder, tmp_path):
    use(recorder, "excel.exe", 350, 370)
    grid = run(recorder, tmp_path, extra=["--tz", "UTC"])["live"]["weekday_hour"]

    assert set(grid) == {"火"}
    assert abs(grid["火"]["14"] - 600) <= 60
    assert abs(grid["火"]["15"] - 600) <= 60


# ------------------------------------------------------------------ #36


def test_symbols_become_labels(recorder, tmp_path):
    past(recorder)
    use(recorder, "excel.exe", 0, 20, title="月次報告.xlsx - Excel")
    use(recorder, "chrome.exe", 21, 25, title="顧客管理 - Chrome")
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))
    text = (out / "analysis_summary.json").read_text(encoding="utf-8")
    result = summary(out)

    assert not re.search(r"[0-9a-f]{16}", text)
    screens = {s["label"]: s for s in result["live"]["screens"]}
    assert screens["ファイル A"]["app"] == "excel.exe"
    assert screens["ファイル A"]["ext"] == ".xlsx"
    assert screens["画面 A"]["app"] == "chrome.exe"
    files = {f["label"] for f in result["past"]["files"]}
    assert files and all(label.startswith("ファイル ") for label in files)


def test_the_same_symbol_keeps_the_same_label(recorder, tmp_path):
    use(recorder, "excel.exe", 0, 5, title="A.xlsx - Excel")
    use(recorder, "chrome.exe", 6, 10, title="B")
    use(recorder, "excel.exe", 11, 15, title="A.xlsx - Excel")
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))
    screens = summary(out)["live"]["screens"]

    assert [s["label"] for s in screens].count("ファイル A") == 1
    assert len(screens) == 2


def test_label_table_is_a_separate_file(recorder, tmp_path):
    past(recorder)
    use(recorder, "excel.exe", 0, 20, title="月次報告.xlsx - Excel")
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))

    tables = list((out.parent / f"{out.name}_do_not_send_to_ai").glob("*.json"))
    assert len(tables) == 1
    labels = json.loads(tables[0].read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{16}", labels["ファイル A"])
    used = json.dumps(summary(out), ensure_ascii=False)
    assert all(label in used for label in labels)
