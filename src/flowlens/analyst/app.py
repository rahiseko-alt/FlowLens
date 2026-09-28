"""flowlens_analyst.exe: the analyst command as a Windows app.

- Double-click: choose the exports, type each password, and the results appear in
  a new folder next to the first export.
- Drop exports onto the exe: the same, without choosing the files.
- With options (e.g. --out): the command line, as `python -m flowlens.analyst`.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from datetime import datetime
from pathlib import Path

from flowlens.analyst.cli import LABELS_DIR_SUFFIX, SUMMARY_FILE, main


def wants_command_line(argv: list[str]) -> bool:
    """Options mean the command line; bare file paths (a drop) mean the window."""
    return any(arg.startswith("-") for arg in argv)


def default_out_dir(first_export: Path, now: datetime) -> Path:
    return first_export.parent / f"FlowLens分析_{now:%Y%m%d_%H%M}"


def run(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if wants_command_line(args):
        return main(args)
    return _run_with_windows([Path(a) for a in args])


def _run_with_windows(exports: list[Path]) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog

    root = tk.Tk()
    root.withdraw()
    title = "FlowLens 分析"
    if not exports:
        chosen = filedialog.askopenfilenames(
            title="分析する診断データ（ZIP）を選んでください（複数可）",
            filetypes=[("FlowLens 診断データ", "*.zip")],
        )
        exports = [Path(p) for p in chosen]
    if not exports:
        return 0

    passwords = {}
    for path in exports:
        answer = simpledialog.askstring(
            title, f"{path.name} のパスワードを入力してください", show="*", parent=root
        )
        if answer is None:
            return 0
        passwords[path.name] = answer

    out = default_out_dir(exports[0], datetime.now())
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
        code = main(
            [*map(str, exports), "--out", str(out)],
            ask_password=lambda prompt: passwords[prompt.split(" のパスワード")[0]],
        )
    if code != 0:
        messagebox.showerror(title, errors.getvalue().strip() or "分析できませんでした。")
        return code

    messagebox.showinfo(
        title,
        "分析が終わりました。\n\n"
        f"結果: {out}\n"
        f"呼び名の対応表（AI に渡さない）: {out.name}{LABELS_DIR_SUFFIX}\n\n"
        f"次に、結果のフォルダで Claude Code を開き、\n"
        f"「instructions_for_claude.md に従って、ご提案書を書いてください」と頼んでください。\n"
        f"（要約は {SUMMARY_FILE} です）",
    )
    if hasattr(os, "startfile"):
        os.startfile(out)  # Windows: open the folder
    return 0
