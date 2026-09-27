from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flowlens.core.recorder import Recorder


class SettingsWindow:
    """Tkinter window for configuring excluded apps, retention, data deletion, and export."""

    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def show(self) -> None:
        root = tk.Tk()
        root.title("FlowLens — 設定・削除・書き出し")
        root.geometry("540x520")
        root.resizable(False, False)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: Excluded Apps
        self._build_excluded_apps_tab(notebook)

        # Tab 2: Retention Policy
        self._build_retention_tab(notebook)

        # Tab 3: Data Deletion
        self._build_deletion_tab(notebook)

        # Tab 4: Diagnostic Export
        self._build_export_tab(notebook)

        root.mainloop()

    def _build_excluded_apps_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding="15")
        notebook.add(tab, text="除外アプリ")

        ttk.Label(
            tab,
            text="記録しないアプリの設定",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Label(
            tab,
            text=(
                "指定したアプリは、ウィンドウ名・打鍵数・操作・クリップボード転送が\n"
                "一切記録されなくなります（追加・削除は即座に反映されます）。"
            ),
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(0, 10))

        # Listbox for current excluded apps
        list_frame = ttk.Frame(tab)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        app_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Segoe UI", 9),
            height=8,
        )
        app_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=app_listbox.yview)

        def refresh_list():
            app_listbox.delete(0, tk.END)
            for app in self.recorder.get_excluded_apps():
                app_listbox.insert(tk.END, app)

        refresh_list()

        # Add entry & button
        add_frame = ttk.Frame(tab)
        add_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(add_frame, text="アプリ名:").pack(side=tk.LEFT, padx=(0, 6))
        entry_app = ttk.Entry(add_frame, width=24)
        entry_app.pack(side=tk.LEFT, padx=(0, 6))
        entry_app.insert(0, "Slack.exe")

        def handle_add():
            val = entry_app.get().strip()
            if val:
                self.recorder.add_excluded_app(val)
                entry_app.delete(0, tk.END)
                refresh_list()

        def handle_remove():
            sel = app_listbox.curselection()
            if sel:
                item = app_listbox.get(sel[0])
                self.recorder.remove_excluded_app(item)
                refresh_list()

        ttk.Button(add_frame, text="追加", command=handle_add).pack(side=tk.LEFT)
        ttk.Button(tab, text="選択したアプリを削除", command=handle_remove).pack(anchor=tk.W)

    def _build_retention_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding="15")
        notebook.add(tab, text="保存期間")

        ttk.Label(
            tab,
            text="データの保存期間設定",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Label(
            tab,
            text="設定した期間を超える古い記録データを自動的に削除します。",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(0, 15))

        cur_days = self.recorder.get_retention_days()
        retention_var = tk.StringVar(value=str(cur_days) if cur_days else "none")

        ttk.Radiobutton(
            tab, text="30 日間（標準）", variable=retention_var, value="30"
        ).pack(anchor=tk.W, pady=4)
        ttk.Radiobutton(tab, text="60 日間", variable=retention_var, value="60").pack(
            anchor=tk.W, pady=4
        )
        ttk.Radiobutton(tab, text="90 日間", variable=retention_var, value="90").pack(
            anchor=tk.W, pady=4
        )
        ttk.Radiobutton(
            tab, text="無期限（削除しない）", variable=retention_var, value="none"
        ).pack(anchor=tk.W, pady=4)

        def handle_save_retention():
            val = retention_var.get()
            days = int(val) if val != "none" else None
            self.recorder.set_retention_days(days)
            self.recorder.apply_retention_policy()
            messagebox.showinfo(
                "設定完了", "保存期間を更新し、対象外の古い記録データを削除しました。"
            )

        ttk.Button(tab, text="設定を保存", command=handle_save_retention).pack(
            anchor=tk.W, pady=(15, 0)
        )

    def _build_deletion_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding="15")
        notebook.add(tab, text="データ削除")

        ttk.Label(
            tab,
            text="記録データの削除",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Label(
            tab,
            text=(
                "指定した範囲の記録データを完全に削除し、空き容量を回収します。\n"
                "※削除されたデータを復元することはできません。"
            ),
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(0, 15))

        scope_frame = ttk.Frame(tab)
        scope_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(scope_frame, text="削除する範囲:").pack(side=tk.LEFT, padx=(0, 8))
        scope_combo = ttk.Combobox(
            scope_frame,
            values=["今日", "過去7日", "過去30日", "すべて"],
            state="readonly",
            width=15,
        )
        scope_combo.set("今日")
        scope_combo.pack(side=tk.LEFT)

        def handle_delete():
            selected = scope_combo.get()
            scope_map = {
                "今日": "today",
                "過去7日": "last_7_days",
                "過去30日": "last_30_days",
                "すべて": "all",
            }
            scope = scope_map.get(selected, "today")

            msg = f"選択した範囲（{selected}）の記録データを完全に削除します。\nよろしいですか？"
            if messagebox.askyesno("削除の確認", msg):
                self.recorder.delete(scope)
                messagebox.showinfo("削除完了", "記録データを正常に削除しました。")

        ttk.Button(tab, text="削除を実行", command=handle_delete).pack(anchor=tk.W)

    def _build_export_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding="15")
        notebook.add(tab, text="書き出し")

        ttk.Label(
            tab,
            text="診断データの書き出し",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Label(
            tab,
            text=(
                "期間とパスワードを指定して、暗号化 ZIP（AES-256）を手元に保存します。\n"
                "生成されたファイルはコンサルタントによる分析に使用されます。"
            ),
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(0, 12))

        # Range selection
        range_frame = ttk.Frame(tab)
        range_frame.pack(fill=tk.X, pady=4)
        ttk.Label(range_frame, text="書き出し期間:", width=14).pack(side=tk.LEFT)
        period_combo = ttk.Combobox(
            range_frame,
            values=["過去7日", "過去14日", "過去30日", "すべて", "日付指定"],
            state="readonly",
            width=18,
        )
        period_combo.set("過去30日")
        period_combo.pack(side=tk.LEFT)

        # Custom date frame (shown when "日付指定" selected)
        custom_frame = ttk.Frame(tab)
        custom_frame.pack(fill=tk.X, pady=4)
        ttk.Label(custom_frame, text="開始日 (YYYY-MM-DD):", width=20).pack(side=tk.LEFT)
        start_entry = ttk.Entry(custom_frame, width=12)
        start_entry.pack(side=tk.LEFT, padx=(0, 8))
        start_entry.insert(0, datetime.now(timezone.utc).strftime("%Y-%m-01"))

        ttk.Label(custom_frame, text="終了日:", width=8).pack(side=tk.LEFT)
        end_entry = ttk.Entry(custom_frame, width=12)
        end_entry.pack(side=tk.LEFT)
        end_entry.insert(0, datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        # Password
        pwd_frame = ttk.Frame(tab)
        pwd_frame.pack(fill=tk.X, pady=4)
        ttk.Label(pwd_frame, text="暗号化パスワード:", width=14).pack(side=tk.LEFT)
        pwd_entry = ttk.Entry(pwd_frame, show="*", width=24)
        pwd_entry.pack(side=tk.LEFT)

        # Destination
        dest_frame = ttk.Frame(tab)
        dest_frame.pack(fill=tk.X, pady=4)
        ttk.Label(dest_frame, text="保存先ファイル:", width=14).pack(side=tk.LEFT)

        today_str = datetime.now().strftime("%Y%m%d")
        default_dir = Path.home() / "Desktop"
        if not default_dir.is_dir():
            default_dir = Path.home()
        default_path = default_dir / f"flowlens_export_{today_str}.zip"

        dest_entry = ttk.Entry(dest_frame, width=28)
        dest_entry.pack(side=tk.LEFT, padx=(0, 6))
        dest_entry.insert(0, str(default_path))

        def handle_browse():
            chosen = filedialog.asksaveasfilename(
                title="書き出し先の選択",
                initialdir=str(default_dir),
                initialfile=f"flowlens_export_{today_str}.zip",
                filetypes=[("ZIP Archive", "*.zip")],
                defaultextension=".zip",
            )
            if chosen:
                dest_entry.delete(0, tk.END)
                dest_entry.insert(0, chosen)

        ttk.Button(dest_frame, text="参照...", command=handle_browse).pack(side=tk.LEFT)

        # Export execution
        def handle_export():
            pwd = pwd_entry.get().strip()
            if not pwd:
                messagebox.showerror("エラー", "暗号化パスワードを入力してください。")
                return

            dest = dest_entry.get().strip()
            if not dest:
                messagebox.showerror("エラー", "保存先ファイルを指定してください。")
                return

            period_text = period_combo.get()
            period_map = {
                "過去7日": "last_7_days",
                "過去14日": "last_14_days",
                "過去30日": "last_30_days",
                "すべて": "all",
                "日付指定": "custom",
            }
            preset = period_map.get(period_text, "last_30_days")

            try:
                if preset == "custom":
                    s_dt = datetime.strptime(start_entry.get().strip(), "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    e_dt = datetime.strptime(end_entry.get().strip(), "%Y-%m-%d").replace(
                        hour=23, minute=59, second=59, tzinfo=timezone.utc
                    )
                    time_range = self.recorder.compute_export_range("custom", s_dt, e_dt)
                else:
                    time_range = self.recorder.compute_export_range(preset)

                saved_path = self.recorder.export(
                    time_range=time_range,
                    password=pwd,
                    destination=dest,
                )
                msg = (
                    "診断データを正常に暗号化して書き出しました。\n\n"
                    f"保存先:\n{saved_path}\n\n"
                    "このファイルとパスワードを分析担当コンサルタントにお渡しください。"
                )
                messagebox.showinfo("書き出し完了", msg)
            except Exception as e:
                messagebox.showerror("書き出しエラー", f"書き出し中にエラーが発生しました:\n{e}")

        ttk.Button(tab, text="診断データを書き出す", command=handle_export).pack(
            anchor=tk.W, pady=(15, 0)
        )
