"""First-run consent screen and the Past Import progress screen (#18)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any

from flowlens.core import Recorder
from flowlens.core.consent import ALL_PAST_SOURCES

SOURCES = {
    "system_log": (
        "Windows のシステムの記録",
        "PC の起動・終了・スリープ・復帰の時刻",
    ),
    "security_log": (
        "Windows のセキュリティの記録",
        "画面ロック・解除・サインアウトの時刻（管理者権限が無いと読めません）",
    ),
    "user_assist": (
        "アプリの利用回数",
        "アプリ（.exe）ごとの起動回数・前面にあった合計時間・最後に使った時刻",
    ),
    "recent_files": (
        "最近使ったファイル",
        "開いたファイルの種類（.xlsx など）と時刻。ファイル名は読めない記号にします",
    ),
    "office_recent": (
        "Office の最近使ったファイル",
        "Word・Excel などで開いたファイルの種類と時刻。ファイル名は読めない記号にします",
    ),
    "browser_history": (
        "Chrome / Edge の閲覧履歴",
        "訪れたサイトの名前（例: example.com）と時刻だけ。ページの中身や URL の続きは読みません",
    ),
}

PRINCIPLES = (
    "FlowLens は、普段の PC 操作から「繰り返している作業」を見つけるための記録アプリです。\n\n"
    "・記録はこの PC の中にだけ保存します。外部への送信や AI の利用は一切しません。\n"
    "・入力した文字、コピーした中身、パスワード、画面は記録しません。\n"
    "・ウィンドウの題名とファイル名は読めない記号に変えて保存します。\n"
    "・画面右下のアイコンで記録中かどうかが分かり、いつでも一時停止できます。\n"
    "・記録しないアプリの指定、記録の削除、書き出しもアイコンから行えます。\n\n"
    "同意すると、これからの記録を始め、あわせて Windows に残っている"
    "過去30日分の足跡を読み込みます。読み込みたくない元はチェックを外してください。"
)


class ConsentDialog:
    def __init__(self) -> None:
        self.consented = False
        self.selected_sources: list[str] = list(ALL_PAST_SOURCES)

    def show(self) -> bool:
        root = tk.Tk()
        root.title("FlowLens — ご利用の前に")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="記録を始める前にご確認ください", font=("", 13, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )
        ttk.Label(frame, text=PRINCIPLES, wraplength=600, justify=tk.LEFT).pack(anchor=tk.W)
        ttk.Label(
            frame, text="過去30日分を読み込む元（初めはすべて選択）", font=("", 10, "bold")
        ).pack(anchor=tk.W, pady=(12, 4))
        choices: dict[str, tk.BooleanVar] = {}
        for source in ALL_PAST_SOURCES:
            title, detail = SOURCES[source]
            choices[source] = tk.BooleanVar(value=True)
            ttk.Checkbutton(frame, text=f"{title} — {detail}", variable=choices[source]).pack(
                anchor=tk.W, pady=1
            )

        def agree() -> None:
            self.selected_sources = [s for s, v in choices.items() if v.get()]
            self.consented = True
            root.destroy()

        def decline() -> None:
            if messagebox.askyesno(
                "確認", "同意しない場合、何も記録・読み込みをせずに終了します。よろしいですか？"
            ):
                self.consented = False
                root.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(buttons, text="同意して記録を始める", command=agree).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="同意しない（終了）", command=decline).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        root.protocol("WM_DELETE_WINDOW", decline)
        root.mainloop()
        return self.consented


def run_past_import_with_progress(
    recorder: Recorder, providers: dict[str, Callable[[], list[Any]]]
) -> dict[str, dict[str, Any]]:
    """Reads each source in the background and shows its progress and result."""
    report: dict[str, dict[str, Any]] = {}
    updates: queue.Queue = queue.Queue()

    def work() -> None:
        for name, provider in providers.items():
            updates.put((name, {"status": "running", "count": 0, "error": None}))
            result = recorder.import_past_providers({name: provider})[name]
            report[name] = result
            updates.put((name, result))
        updates.put(None)

    root = tk.Tk()
    root.title("FlowLens — 過去30日分の読み込み")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill=tk.BOTH, expand=True)
    heading = ttk.Label(frame, text="過去30日分の足跡を読み込んでいます…", font=("", 12, "bold"))
    heading.pack(anchor=tk.W, pady=(0, 8))
    table = ttk.Treeview(frame, columns=("state", "count", "reason"), height=len(providers))
    for col, text, width in (
        ("#0", "読み込む元", 220),
        ("state", "状態", 90),
        ("count", "件数", 70),
        ("reason", "読めなかった理由", 220),
    ):
        table.heading(col, text=text)
        table.column(col, width=width)
    for name in providers:
        table.insert(
            "", tk.END, iid=name, text=SOURCES.get(name, (name,))[0], values=("待機中", "", "")
        )
    table.pack(fill=tk.BOTH)
    close = ttk.Button(frame, text="閉じる", command=root.destroy, state=tk.DISABLED)
    close.pack(anchor=tk.E, pady=(12, 0))
    labels = {
        "running": "読み込み中",
        "success": "完了",
        "partial": "一部のみ",
        "skipped": "対象外",
        "failed": "読めず",
    }

    def poll() -> None:
        while True:
            try:
                item = updates.get_nowait()
            except queue.Empty:
                root.after(200, poll)
                return
            if item is None:
                heading.config(text="読み込みが終わりました")
                close.config(state=tk.NORMAL)
                return
            name, result = item
            reason = result["error"] or "" if result["status"] in ("failed", "partial") else ""
            table.item(name, values=(labels[result["status"]], result["count"] or "", reason))

    threading.Thread(target=work, name="past-import", daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", lambda: close.instate(["!disabled"]) and root.destroy())
    root.after(200, poll)
    root.mainloop()
    return report
