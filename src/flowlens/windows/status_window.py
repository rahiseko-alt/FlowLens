"""Status screen: recording or paused, since when, how long, how much disk (#18)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from tkinter import ttk

from flowlens.core import Recorder


def format_duration(seconds: float) -> str:
    minutes = int(seconds) // 60
    return f"{minutes // 60}時間{minutes % 60}分"


def format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / 1024:.0f} KB"


class StatusWindow:
    def __init__(
        self,
        recorder: Recorder,
        consent_date: datetime | None,
        on_toggle: Callable[[], None] | None = None,
    ):
        self.recorder = recorder
        self.consent_date = consent_date
        self.on_toggle = on_toggle

    def show(self) -> None:
        status = self.recorder.get_status()
        root = tk.Tk()
        root.title("FlowLens — 記録の状態")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        state = tk.StringVar()
        started = (
            self.consent_date.astimezone().strftime("%Y年%m月%d日") if self.consent_date else "—"
        )
        rows = [
            ("状態", state),
            ("収集開始日", started),
            ("記録済みの時間", format_duration(status["recorded_seconds"])),
            ("データ使用量", format_bytes(status["database_size_bytes"])),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=3, padx=(0, 16))
            if isinstance(value, tk.StringVar):
                ttk.Label(frame, textvariable=value, font=("", 10, "bold")).grid(
                    row=i, column=1, sticky=tk.W
                )
            else:
                ttk.Label(frame, text=value).grid(row=i, column=1, sticky=tk.W)

        button = ttk.Button(frame)

        def render() -> None:
            paused = self.recorder.is_paused
            state.set("一時停止中" if paused else "記録中")
            button.config(text="記録を再開する" if paused else "一時停止する")

        def toggle() -> None:
            if self.recorder.is_paused:
                self.recorder.resume()
            else:
                self.recorder.pause()
            render()
            if self.on_toggle:
                self.on_toggle()

        button.config(command=toggle)
        button.grid(row=len(rows), column=0, pady=(16, 0), sticky=tk.W)
        ttk.Button(frame, text="閉じる", command=root.destroy).grid(
            row=len(rows), column=1, pady=(16, 0), sticky=tk.E
        )
        render()
        root.mainloop()
