"""#37 Scheduled-file candidates (Past Import) and the candidate list."""

from __future__ import annotations

from datetime import timedelta

from analyst_support import run
from conftest import T0

from flowlens.core import PastFileObservation

DAY = timedelta(days=1)
NINE_JST = T0 - timedelta(hours=9)  # T0 is 09:00 UTC = 18:00 JST; this is 09:00 JST


def opens(recorder, name, times):
    recorder.import_past_providers(
        {"recent_files": lambda: [PastFileObservation(name, t) for t in times]}
    )


def test_a_file_opened_every_morning_is_a_candidate(recorder, tmp_path):
    opens(
        recorder,
        "日報.xlsx",
        [NINE_JST - k * DAY + timedelta(minutes=5 * k) for k in range(1, 5)],
    )
    opens(recorder, "一度だけ.docx", [NINE_JST - 2 * DAY])
    candidates = run(recorder, tmp_path)["candidates"]

    assert len(candidates) == 1
    c = candidates[0]
    assert c["kind"] == "定時のファイル"
    assert c["labels"] == ["ファイル A"]
    assert c["count"] == 4 and c["days"] == 4
    assert c["timing"] == {"hour": 9, "share": 1.0}


def test_estimate_is_marked_and_explained(recorder, tmp_path):
    opens(recorder, "日報.xlsx", [NINE_JST - k * DAY for k in range(1, 4)])
    c = run(recorder, tmp_path)["candidates"][0]

    assert c["monthly_minutes_estimate"] is None  # how long each time is not known
    assert c["formula"]
    assert "推定" in c["estimate_note"]


def test_criteria_can_be_changed(recorder, tmp_path):
    opens(recorder, "日報.xlsx", [NINE_JST - k * DAY for k in range(1, 4)])  # 3 days
    result = run(recorder, tmp_path, extra=["--min-days", "4"])

    assert result["candidates"] == []
    assert result["criteria"] == {"min_days": 4, "min_count": 3}


def test_the_same_day_does_not_count_as_repetition_across_days(recorder, tmp_path):
    opens(recorder, "日報.xlsx", [NINE_JST - DAY + timedelta(minutes=m) for m in (0, 10, 20)])
    assert run(recorder, tmp_path)["candidates"] == []  # 3 times, but on 1 day
