from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from flowlens.core.recorder import Recorder


def format_duration(seconds: float) -> str:
    """Formats seconds into human readable X時間Y分Z秒."""
    total_secs = int(seconds)
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    secs = total_secs % 60
    if hours > 0:
        return f"{hours}時間{minutes}分{secs}秒"
    if minutes > 0:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def format_bytes(b: int) -> str:
    """Formats bytes into human readable KB / MB."""
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.2f} MB"
    if b >= 1024:
        return f"{b / 1024:.2f} KB"
    return f"{b} B"


class StatusWindow:
    """Tkinter window displaying collector operational status, duration, and disk usage."""

    def __init__(
        self,
        recorder: Recorder,
        on_toggle_pause: Callable[[], None] | None = None,
    ):
        self.recorder = recorder
        self.on_toggle_pause = on_toggle_pause

    def show(self) -> None:
        root = tk.Tk()
        root.title("FlowLens — 記録状態")
        root.geometry("420x300")
        root.resizable(False, False)

        frame = ttk.Frame(root, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="FlowLens 記録状態", font=("Segoe UI", 13, "bold")).pack(
            anchor=tk.W, pady=(0, 15)
        )

        status = self.recorder.get_status()

        # Labels frame
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=tk.X, pady=(0, 15))

        # Status text
        is_rec = status["is_recording"]
        state_str = "● 記録中" if is_rec else "⏸ 一時停止中"
        state_color = "#2e7d32" if is_rec else "#d32f2f"

        ttk.Label(info_frame, text="動作状態: ", font=("Segoe UI", 10)).grid(
            row=0, column=0, sticky=tk.W, pady=4
        )
        lbl_state = tk.Label(
            info_frame,
            text=state_str,
            fg=state_color,
            font=("Segoe UI", 10, "bold"),
        )
        lbl_state.grid(row=0, column=1, sticky=tk.W, pady=4)

        # Start date
        start_str = "未記録"
        if status.get("earliest_session"):
            try:
                dt = datetime.fromisoformat(status["earliest_session"]).astimezone(timezone.utc)
                start_str = dt.strftime("%Y-%m-%d %H:%M:%S (UTC)")
            except ValueError:
                start_str = str(status["earliest_session"])

        ttk.Label(info_frame, text="収集開始日時: ", font=("Segoe UI", 10)).grid(
            row=1, column=0, sticky=tk.W, pady=4
        )
        ttk.Label(info_frame, text=start_str, font=("Segoe UI", 10)).grid(
            row=1, column=1, sticky=tk.W, pady=4
        )

        # Recorded duration
        dur_str = format_duration(status["total_duration_seconds"])
        ttk.Label(info_frame, text="記録済み時間: ", font=("Segoe UI", 10)).grid(
            row=2, column=0, sticky=tk.W, pady=4
        )
        ttk.Label(info_frame, text=dur_str, font=("Segoe UI", 10)).grid(
            row=2, column=1, sticky=tk.W, pady=4
        )

        # Data usage
        db_size_str = format_bytes(status["database_size_bytes"])
        ttk.Label(info_frame, text="データ使用量: ", font=("Segoe UI", 10)).grid(
            row=3, column=0, sticky=tk.W, pady=4
        )
        ttk.Label(info_frame, text=db_size_str, font=("Segoe UI", 10)).grid(
            row=3, column=1, sticky=tk.W, pady=4
        )

        # Control buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        def toggle_pause():
            if self.recorder.is_paused:
                self.recorder.resume()
                lbl_state.config(text="● 記録中", fg="#2e7d32")
                btn_pause.config(text="一時停止")
            else:
                self.recorder.pause()
                lbl_state.config(text="⏸ 一時停止中", fg="#d32f2f")
                btn_pause.config(text="再開")
            if self.on_toggle_pause:
                self.on_toggle_pause()

        btn_pause_text = "再開" if status["is_paused"] else "一時停止"
        btn_pause = ttk.Button(btn_frame, text=btn_pause_text, command=toggle_pause)
        btn_pause.pack(side=tk.LEFT)

        btn_close = ttk.Button(btn_frame, text="閉じる", command=root.destroy)
        btn_close.pack(side=tk.RIGHT)

        root.mainloop()
