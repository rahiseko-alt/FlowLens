"""Settings: excluded apps, retention, deletion, export, and reading more past sources (#20)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from flowlens.core import Recorder
from flowlens.core.consent import ALL_PAST_SOURCES
from flowlens.windows.consent_dialog import SOURCES

EXPORT_PERIODS = {
    "過去7日": "last_7_days",
    "過去14日": "last_14_days",
    "過去30日": "last_30_days",
    "すべて": "all",
    "日付を指定": "custom",
}
DELETE_SCOPES = {
    "今日": "today",
    "過去7日": "last_7_days",
    "過去30日": "last_30_days",
    "すべて": "all",
}
RETENTION = {"30日": 30, "60日": 60, "90日": 90, "無期限": None}


class SettingsWindow:
    def __init__(
        self,
        recorder: Recorder,
        read_more_sources: Callable[[list[str]], dict[str, Any]],
    ):
        self.recorder = recorder
        self.read_more_sources = read_more_sources

    def show(self) -> None:
        self.root = tk.Tk()
        self.root.title("FlowLens — 設定・削除・書き出し")
        self.root.resizable(False, False)
        tabs = ttk.Notebook(self.root)
        tabs.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for title, build in (
            ("診断データの書き出し", self._export_tab),
            ("記録しないアプリ", self._exclusion_tab),
            ("保存期間", self._retention_tab),
            ("記録の削除", self._delete_tab),
            ("過去の足跡", self._past_tab),
        ):
            tab = ttk.Frame(tabs, padding=16)
            tabs.add(tab, text=title)
            build(tab)
        self.root.mainloop()

    # ------------------------------------------------------------------ export

    def _export_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(
            tab,
            text="期間とパスワードを決めると、暗号化した1つのファイルを保存します。\n"
            "ファイルとパスワードは、別々の方法でコンサルタントに渡してください。",
            justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 12))

        period = ttk.Combobox(tab, values=list(EXPORT_PERIODS), state="readonly", width=14)
        period.set("過去30日")
        today = datetime.now().strftime("%Y-%m-%d")
        start, end = ttk.Entry(tab, width=12), ttk.Entry(tab, width=12)
        start.insert(0, today[:8] + "01")
        end.insert(0, today)
        password, confirm = ttk.Entry(tab, show="*", width=24), ttk.Entry(tab, show="*", width=24)
        default = Path.home() / "Desktop"
        if not default.is_dir():
            default = Path.home()
        dest = ttk.Entry(tab, width=40)
        dest.insert(0, str(default / f"FlowLens診断データ_{datetime.now():%Y%m%d}.zip"))

        rows = [
            ("期間", period),
            ("開始日（日付を指定のとき）", start),
            ("終了日（日付を指定のとき）", end),
            ("パスワード", password),
            ("パスワード（確認）", confirm),
            ("保存先", dest),
        ]
        for i, (label, widget) in enumerate(rows, start=1):
            ttk.Label(tab, text=label).grid(row=i, column=0, sticky=tk.W, pady=3, padx=(0, 8))
            widget.grid(row=i, column=1, sticky=tk.W)

        def browse() -> None:
            chosen = filedialog.asksaveasfilename(
                initialfile=Path(dest.get()).name,
                initialdir=str(Path(dest.get()).parent),
                defaultextension=".zip",
                filetypes=[("ZIP", "*.zip")],
            )
            if chosen:
                dest.delete(0, tk.END)
                dest.insert(0, chosen)

        ttk.Button(tab, text="参照…", command=browse).grid(row=len(rows), column=2, padx=(6, 0))

        def run() -> None:
            if not password.get():
                messagebox.showerror("書き出し", "パスワードを入力してください。")
                return
            if password.get() != confirm.get():
                messagebox.showerror("書き出し", "確認用のパスワードが一致しません。")
                return
            preset = EXPORT_PERIODS[period.get()]
            try:
                if preset == "custom":
                    first = datetime.combine(_date(start.get()), time.min).astimezone()
                    last = datetime.combine(_date(end.get()), time.max).astimezone()
                    rng = self.recorder.compute_export_range("custom", first, last)
                else:
                    rng = self.recorder.compute_export_range(preset)
                path = self.recorder.export(rng, password.get(), dest.get())
            except ValueError as exc:
                messagebox.showerror("書き出し", f"書き出せませんでした: {exc}")
                return
            except OSError as exc:
                messagebox.showerror("書き出し", f"保存できませんでした（{type(exc).__name__}）")
                return
            messagebox.showinfo("書き出し", f"保存しました。\n\n{path}")

        ttk.Button(tab, text="診断データを書き出す", command=run).grid(
            row=len(rows) + 1, column=0, columnspan=2, sticky=tk.W, pady=(16, 0)
        )

    # ------------------------------------------------------------------ exclusions

    def _exclusion_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(
            tab,
            text="ここに入れたアプリを使っている間は、使っていた時間以外は何も記録しません。\n"
            "（例: keepass.exe、line.exe）すでに記録した分も、書き出しから除かれます。",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 8))
        listbox = tk.Listbox(tab, height=8, width=40)
        listbox.pack(anchor=tk.W)

        def refresh() -> None:
            listbox.delete(0, tk.END)
            for app in self.recorder.get_excluded_apps():
                listbox.insert(tk.END, app)

        row = ttk.Frame(tab)
        row.pack(anchor=tk.W, pady=8)
        entry = ttk.Entry(row, width=28)
        entry.pack(side=tk.LEFT)

        def add() -> None:
            try:
                self.recorder.add_excluded_app(entry.get())
            except ValueError:
                messagebox.showerror("記録しないアプリ", "「〇〇.exe」の形で入力してください。")
                return
            entry.delete(0, tk.END)
            refresh()

        def remove() -> None:
            for index in listbox.curselection():
                self.recorder.remove_excluded_app(listbox.get(index))
            refresh()

        ttk.Button(row, text="追加", command=add).pack(side=tk.LEFT, padx=6)
        ttk.Button(tab, text="選んだアプリを外す", command=remove).pack(anchor=tk.W)
        refresh()

    # ------------------------------------------------------------------ retention

    def _retention_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="この期間より古い記録は自動で削除します。").pack(
            anchor=tk.W, pady=(0, 8)
        )
        current = self.recorder.get_retention_days()
        choice = tk.StringVar(value=next(k for k, v in RETENTION.items() if v == current))
        for label in RETENTION:
            ttk.Radiobutton(tab, text=label, value=label, variable=choice).pack(anchor=tk.W)

        def save() -> None:
            self.recorder.set_retention_days(RETENTION[choice.get()])
            messagebox.showinfo("保存期間", "保存期間を変更しました。")

        ttk.Button(tab, text="変更する", command=save).pack(anchor=tk.W, pady=(12, 0))

    # ------------------------------------------------------------------ deletion

    def _delete_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="選んだ範囲の記録を削除します。元に戻せません。").pack(
            anchor=tk.W, pady=(0, 8)
        )
        scope = ttk.Combobox(tab, values=list(DELETE_SCOPES), state="readonly", width=12)
        scope.set("今日")
        scope.pack(anchor=tk.W)

        def delete() -> None:
            if messagebox.askyesno(
                "記録の削除", f"「{scope.get()}」の記録を削除します。よろしいですか？"
            ):
                self.recorder.delete(DELETE_SCOPES[scope.get()])
                messagebox.showinfo("記録の削除", "削除しました。")

        ttk.Button(tab, text="削除する", command=delete).pack(anchor=tk.W, pady=(12, 0))

    # ------------------------------------------------------------------ past sources

    def _past_tab(self, tab: ttk.Frame) -> None:
        enabled = self.recorder.get_enabled_past_sources()
        missing = [s for s in ALL_PAST_SOURCES if enabled is not None and s not in enabled]
        if not missing:
            ttk.Label(tab, text="すべての元から読み込み済みです。").pack(anchor=tk.W)
            return
        ttk.Label(
            tab, text="初めに外した元を、あとから読み込めます（今から30日前までの分）。"
        ).pack(anchor=tk.W, pady=(0, 8))
        choices = {s: tk.BooleanVar(value=False) for s in missing}
        for source, var in choices.items():
            title, detail = SOURCES[source]
            ttk.Checkbutton(tab, text=f"{title} — {detail}", variable=var).pack(anchor=tk.W)

        def read() -> None:
            chosen = [s for s, v in choices.items() if v.get()]
            if chosen:
                self.root.destroy()
                self.read_more_sources(chosen)

        ttk.Button(tab, text="読み込む", command=read).pack(anchor=tk.W, pady=(12, 0))


def _date(text: str) -> date:
    return datetime.strptime(text.strip(), "%Y-%m-%d").date()
