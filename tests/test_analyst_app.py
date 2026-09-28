"""The Windows app wrapper: which mode, and where results go."""

from datetime import datetime
from pathlib import Path

from flowlens.analyst.app import default_out_dir, wants_command_line


def test_options_mean_the_command_line_and_bare_files_mean_the_window():
    assert wants_command_line(["a.zip", "--out", "x"])
    assert not wants_command_line(["C:/Users/a/Desktop/a.zip", "b.zip"])  # dropped files
    assert not wants_command_line([])  # double-click


def test_results_go_next_to_the_first_export():
    out = default_out_dir(Path("/desk/FlowLens診断データ.zip"), datetime(2026, 9, 28, 14, 5))
    assert out == Path("/desk/FlowLens分析_20260928_1405")
