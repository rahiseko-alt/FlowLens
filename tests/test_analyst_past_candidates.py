"""Candidates and time use from Past Import alone, for the proposal 3 days after install.

Found with real data: Windows keeps only the last open of each recent file, so a
file never shows up on several days. Sites and PC on/off times do.
"""

from __future__ import annotations

from datetime import timedelta

from analyst_support import analyze, make_export, run
from conftest import T0

from flowlens.core import PastBrowserObservation, PastSystemEventObservation
from flowlens.windows.past_import import user_assist_app

DAY = timedelta(days=1)
NINE_JST = T0 - timedelta(hours=9)  # T0 is 09:00 UTC = 18:00 JST; this is 09:00 JST


def visits(recorder, domain, days, per_day=1):
    recorder.import_past_providers(
        {
            "browser_history": lambda: [
                PastBrowserObservation(domain, NINE_JST - k * DAY + timedelta(minutes=10 * n))
                for k in range(1, days + 1)
                for n in range(per_day)
            ]
        }
    )


def sites(result):
    return [c for c in result["candidates"] if c["kind"] == "よく使うサイト"]


def test_a_site_used_on_many_days_is_a_candidate(recorder, tmp_path):
    visits(recorder, "trimmer.example.com", days=6, per_day=2)
    found = sites(run(recorder, tmp_path))

    assert len(found) == 1
    c = found[0]
    assert c["steps"] == ["trimmer.example.com"]
    assert c["days"] == 6 and c["count"] == 6  # two opens 10 minutes apart are one use
    assert c["timing"]["hour"] == 9
    assert c["monthly_minutes_estimate"] is None and "推定" in c["estimate_note"]


def test_a_site_on_a_few_days_or_a_sign_in_page_is_not(recorder, tmp_path):
    visits(recorder, "news.example.com", days=3, per_day=2)
    visits(recorder, "accounts.google.com", days=10)
    visits(recorder, "auth.example.com", days=10)
    assert sites(run(recorder, tmp_path)) == []


def test_pc_hours_per_day_from_on_and_off_times(recorder, tmp_path):
    events = []
    for k in range(1, 4):
        day = NINE_JST - k * DAY
        events += [
            PastSystemEventObservation("boot", day - timedelta(minutes=30)),  # 08:30 JST
            PastSystemEventObservation("sleep", day + timedelta(hours=9)),  # 18:00 JST
        ]
    recorder.import_past_providers({"system_log": lambda: events})
    hours = run(recorder, tmp_path)["past"]["pc_hours"]

    assert hours["days"] == 3
    assert hours["typical_first"] == "08:30"
    assert hours["typical_last"] == "18:00"
    assert sum(hours["days_by_weekday"].values()) == 3


def test_user_assist_names_become_apps():
    assert user_assist_app("{6D809377}\\Google\\Chrome\\Application\\chrome.exe") == "chrome.exe"
    assert user_assist_app("Microsoft.Office.EXCEL.EXE.15") == "excel.exe"
    assert user_assist_app("Chrome") == "chrome.exe"
    assert user_assist_app("Microsoft.WindowsCalculator_8wekyb3d8bbwe!App")
    assert user_assist_app("{A77F5D77}\\TaskBar\\顧客リスト.lnk") is None
    assert user_assist_app("見積もり 山田様") is None


def test_a_site_candidate_gets_a_question(recorder, tmp_path):
    visits(recorder, "trimmer.example.com", days=6)
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))
    questions = (out / "confirmation_questions.md").read_text(encoding="utf-8")
    assert "trimmer.example.com" in questions and "6日" in questions


def test_search_sns_and_video_sites_are_not_candidates(recorder, tmp_path):
    for domain in (
        "www.google.com",
        "www.bing.com",
        "www.youtube.com",
        "x.com",
        "myaccount.google.com",
    ):
        visits(recorder, domain, days=10)
    visits(recorder, "docs.google.com", days=10)
    assert [c["steps"][0] for c in sites(run(recorder, tmp_path))] == ["docs.google.com"]


def test_opens_close_together_count_as_one_use(recorder, tmp_path):
    visits(recorder, "crm.example.com", days=6, per_day=3)  # 3 opens within 20 minutes a day
    c = sites(run(recorder, tmp_path))[0]
    assert c["count"] == 6


def test_at_most_five_candidates_of_a_kind(recorder, tmp_path):
    for n in range(8):
        visits(recorder, f"tool{n}.example.com", days=5 + n)
    result = run(recorder, tmp_path)

    assert [c["steps"][0] for c in sites(result)] == [
        f"tool{n}.example.com" for n in (7, 6, 5, 4, 3)
    ]
    assert result["candidates_left_out"] == {"よく使うサイト": 3}
