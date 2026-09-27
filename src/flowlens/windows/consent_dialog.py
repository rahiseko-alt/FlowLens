from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from flowlens.core.consent import ALL_PAST_SOURCES

SOURCE_LABELS = {
    "system_log": "システムログ（起動・終了・スリープ時刻）",
    "security_log": "セキュリティログ（ログオン・ロック時刻 ※管理者権限が必要）",
    "srum": "システム資源利用記録（SRUM ※管理者権限が必要）",
    "user_assist": "アプリ起動履歴（UserAssist）",
    "recent_files": "最近使ったファイル（開いたファイル拡張子）",
    "office_recent": "Office の最近使ったファイル",
    "browser_history": "ブラウザ閲覧履歴（訪問ドメインのみ、本文・URLクエリは除外）",
}


class ConsentDialog:
    """Tkinter-based first-run consent dialog presenting privacy commitments and choices."""

    def __init__(
        self,
        on_consent: Callable[[list[str]], None] | None = None,
        on_decline: Callable[[], None] | None = None,
    ):
        self.on_consent = on_consent
        self.on_decline = on_decline
        self.consented = False
        self.selected_sources: list[str] = list(ALL_PAST_SOURCES)

    def show(self) -> bool:
        """Displays the consent modal dialog. Returns True if user consented, False otherwise."""
        root = tk.Tk()
        root.title("FlowLens — 初回利用同意と過去データの読み込み")
        root.geometry("640x680")
        root.resizable(False, False)

        # Main frame
        frame = ttk.Frame(root, padding="16 16 16 16")
        frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            frame,
            text="FlowLens 業務記録の利用開始",
            font=("Segoe UI", 14, "bold"),
        )
        title_label.pack(anchor=tk.W, pady=(0, 10))

        # Privacy Commitments Box
        privacy_text = (
            "【プライバシー保護の原則】\n"
            "・データはすべてお使いの PC 内（ローカル）にのみ保存されます。\n"
            "・外部サーバーやクラウドへの送信、AI/LLM の呼び出しは一切行いません。\n"
            "・入力した文字、文章、クリップボードの内容、パスワードは記録されません。\n"
            "・ウィンドウ名やファイル名は読めない記号に変換し、URL はドメイン名のみ保存します。\n"
            "・右下のタスクトレイアイコンから、いつでも一時停止や記録データの削除が可能です。\n\n"
            "【過去30日分の足跡の読み込み】\n"
            "インストール後すぐに分析提案を行うため、Windows やアプリが既に残している"
            "過去30日分の足跡を読み込みます。"
            "読み込みたくない元は以下のチェックを外して除外できます。"
        )
        msg_box = tk.Text(
            frame,
            height=9,
            wrap=tk.WORD,
            bg="#f4f4f4",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=10,
            pady=8,
        )
        msg_box.insert(tk.END, privacy_text)
        msg_box.config(state=tk.DISABLED)
        msg_box.pack(fill=tk.X, pady=(0, 12))

        # Checkboxes header
        ttk.Label(
            frame,
            text="読み込む元の選択（初期状態ですべて選択）:",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W, pady=(0, 6))

        # Sources checkboxes frame
        chk_frame = ttk.Frame(frame)
        chk_frame.pack(fill=tk.X, pady=(0, 16))

        var_dict: dict[str, tk.BooleanVar] = {}
        for src in ALL_PAST_SOURCES:
            var = tk.BooleanVar(value=True)
            var_dict[src] = var
            lbl = SOURCE_LABELS.get(src, src)
            chk = ttk.Checkbutton(chk_frame, text=lbl, variable=var)
            chk.pack(anchor=tk.W, pady=2)

        # Progress / Status section (initially empty)
        status_label = ttk.Label(frame, text="", font=("Segoe UI", 9))
        status_label.pack(anchor=tk.W, pady=(0, 8))

        # Buttons frame
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        def handle_agree():
            chosen = [src for src, var in var_dict.items() if var.get()]
            self.selected_sources = chosen
            self.consented = True
            if self.on_consent:
                self.on_consent(chosen)
            root.destroy()

        def handle_decline():
            msg = (
                "同意しない場合、FlowLens は何も記録・読み込みを行わずに終了します。"
                "よろしいですか？"
            )
            if messagebox.askyesno("確認", msg):
                self.consented = False
                if self.on_decline:
                    self.on_decline()
                root.destroy()

        btn_agree = ttk.Button(btn_frame, text="同意して記録を開始", command=handle_agree)
        btn_agree.pack(side=tk.RIGHT, padx=(8, 0))

        btn_decline = ttk.Button(btn_frame, text="同意しない（終了）", command=handle_decline)
        btn_decline.pack(side=tk.RIGHT)

        root.protocol("WM_DELETE_WINDOW", handle_decline)
        root.mainloop()
        return self.consented


def show_import_results_dialog(report: dict[str, dict[str, Any]]) -> None:
    """Displays the result of Past Import (record counts and reasons for unread sources)."""
    root = tk.Tk()
    root.title("FlowLens — 過去データ読み込み結果")
    root.geometry("520x380")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding="16")
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(
        frame,
        text="過去30日分の読み込みが完了しました",
        font=("Segoe UI", 12, "bold"),
    ).pack(anchor=tk.W, pady=(0, 10))

    tree = ttk.Treeview(frame, columns=("source", "status", "count", "reason"), show="headings")
    tree.heading("source", text="読み込み元")
    tree.heading("status", text="結果")
    tree.heading("count", text="件数")
    tree.heading("reason", text="理由")

    tree.column("source", width=120)
    tree.column("status", width=60)
    tree.column("count", width=50)
    tree.column("reason", width=220)

    for src, res in report.items():
        st = res["status"]
        status = "成功" if st == "success" else ("除外" if st == "skipped" else "失敗")
        cnt = str(res["count"])
        err = res.get("error") or ""
        tree.insert("", tk.END, values=(src, status, cnt, err))

    tree.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    btn = ttk.Button(frame, text="閉じる", command=root.destroy)
    btn.pack(side=tk.RIGHT)

    root.mainloop()
