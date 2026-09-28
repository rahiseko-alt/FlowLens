"""Build check for flowlens_analyst.exe: a real export in, the result folder out.

Usage: python installer/analyst_smoke.py dist/flowlens_analyst.exe
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flowlens.core import Recorder, TimeRange, WindowObservation


def main(exe: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        start = datetime.now(timezone.utc) - timedelta(days=2)
        recorder = Recorder(tmp_path / "data", clock=lambda: start + timedelta(days=1))
        for minute in range(30):
            app = "outlook.exe" if minute < 15 else "excel.exe"
            recorder.observe(WindowObservation(start + timedelta(minutes=minute), app))
        recorder.flush()
        export = tmp_path / "export.zip"
        recorder.export(
            TimeRange(start - timedelta(days=1), start + timedelta(days=1)), "pw", export
        )
        recorder.storage.close()

        out = tmp_path / "result"
        env = {**os.environ, "FLOWLENS_PASSWORD": "pw"}
        done = subprocess.run([exe, str(export), "--out", str(out)], env=env, timeout=300)
        if done.returncode != 0:
            print(f"analyst exited with {done.returncode}")
            return 1
        summary = json.loads((out / "analysis_summary.json").read_text(encoding="utf-8"))
        assert summary["live"]["app_time"], summary
        for name in ("confirmation_questions.md", "instructions_for_claude.md"):
            assert (out / name).is_file(), name
        assert (tmp_path / "result_do_not_send_to_ai" / "labels.json").is_file()
        print("analyst ok:", [a["app"] for a in summary["live"]["app_time"]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
