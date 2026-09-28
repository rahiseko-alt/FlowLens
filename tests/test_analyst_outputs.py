"""#41 The output folder: summary, confirmation questions, instructions, label table."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pyzipper
from analyst_support import analyze, make_export, summary
from conftest import PASSWORD, T0, at, use

from flowlens.core import ClipboardObservation, PastFileObservation

DAY = 24 * 60


def busy_week(recorder):
    recorder.import_past_providers(
        {
            "recent_files": lambda: [
                PastFileObservation("日報.xlsx", T0 - timedelta(days=k, hours=9)) for k in (1, 2, 3)
            ]
        }
    )
    for day in range(3):
        base = day * DAY
        use(recorder, "outlook.exe", base, base + 2)
        use(recorder, "chrome.exe", base + 3, base + 5)
        recorder.observe(ClipboardObservation(at(base + 5), "copy", app_name="chrome.exe"))
        use(recorder, "excel.exe", base + 6, base + 8, title="台帳.xlsx - Excel")
        recorder.observe(ClipboardObservation(at(base + 7), "paste", app_name="excel.exe"))


def test_the_folder_always_has_the_same_shape(recorder, tmp_path):
    busy_week(recorder)
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))

    assert code == 0
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "analysis_summary.json",
        "confirmation_questions.md",
        "instructions_for_claude.md",
    ]
    assert (out.parent / f"{out.name}_do_not_send_to_ai" / "labels.json").is_file()


def test_every_candidate_has_a_question(recorder, tmp_path):
    busy_week(recorder)
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))
    questions = (out / "confirmation_questions.md").read_text(encoding="utf-8")
    candidates = summary(out)["candidates"]

    assert {c["kind"] for c in candidates} >= {"定時のファイル", "流れ", "転記"}
    for number, c in enumerate(candidates, start=1):
        assert f"候補 {number}" in questions
        for label in c["labels"]:
            assert label in questions


def test_no_symbols_or_device_ids_in_what_the_ai_or_employees_see(recorder, tmp_path):
    busy_week(recorder)
    export = make_export(recorder, tmp_path)
    with pyzipper.AESZipFile(export) as zf:
        zf.setpassword(PASSWORD.encode())
        device = json.loads(zf.read("manifest.json"))["device_id"]
    code, out = analyze(tmp_path, export)

    for name in ("confirmation_questions.md", "instructions_for_claude.md"):
        text = (out / name).read_text(encoding="utf-8")
        assert device not in text
        assert not re.search(r"[0-9a-f]{16}", text)


def test_instructions_state_the_rules(recorder, tmp_path):
    busy_week(recorder)
    code, out = analyze(tmp_path, make_export(recorder, tmp_path))
    text = (out / "instructions_for_claude.md").read_text(encoding="utf-8")

    for rule in (
        "analysis_summary.json",  # the only thing to read
        "do_not_send_to_ai",  # never read
        "数字",  # numbers only from the summary
        "推定",  # estimates marked as estimates
        "個人",  # no comparing people
        "3〜5",  # 3-5 candidates
        "confirmation_questions.md",  # attach the questions
    ):
        assert rule in text
