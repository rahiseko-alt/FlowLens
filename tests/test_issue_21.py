import ast
import os
import socket
import tempfile
import urllib.request
from pathlib import Path

from flowlens.core.models import (
    ClipboardObservation,
    ControlMetadataObservation,
    IdleObservation,
    PastBrowserObservation,
    TimeRange,
    TypingObservation,
    WindowObservation,
)
from flowlens.core.recorder import Recorder
from flowlens.windows.installer import uninstall_app


def test_no_network_connections_during_full_lifecycle(monkeypatch):
    """記録・Past Import・書き出しの間に外部への通信が一切発生しないことをテストで確かめる"""

    def fail_network(*args, **kwargs):
        raise RuntimeError("Prohibited network connection attempted!")

    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)

    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = Recorder(storage_dir=tmpdir)

        # 1. Live capture observations
        now = recorder.clock()
        recorder.observe(
            WindowObservation(app_name="App.exe", window_title="Doc.txt", timestamp=now)
        )
        recorder.observe(IdleObservation(is_idle=False, timestamp=now))
        recorder.observe(
            TypingObservation(keystrokes=15, duration_seconds=5.0, timestamp=now)
        )
        recorder.observe(
            ClipboardObservation(
                action="copy", data_type="text", data_length=20, timestamp=now
            )
        )
        recorder.observe(
            ControlMetadataObservation(
                control_type="Button",
                automation_id="SubmitBtn",
                class_name="Button",
                framework_id="Win32",
                state="Normal",
                timestamp=now,
            )
        )
        recorder.flush()

        # 2. Past Import
        recorder.import_past_records(
            "browser_history",
            [
                PastBrowserObservation(
                    url="https://internal.company.com/home",
                    timestamp=now,
                    source="browser_history",
                )
            ],
        )

        # 3. Export
        dest_zip = os.path.join(tmpdir, "export.zip")
        recorder.export(
            time_range=TimeRange(start=now, end=now),
            password="pwd",
            destination=dest_zip,
        )

        assert os.path.exists(dest_zip)


def test_codebase_contains_no_networking_or_ai_libraries():
    """配布物（src/flowlens）に通信ライブラリ（REST、AI、更新確認等）が含まれない"""
    banned_modules = {
        "requests",
        "httpx",
        "urllib3",
        "aiohttp",
        "fastapi",
        "flask",
        "uvicorn",
        "websockets",
        "openai",
        "anthropic",
        "google.genai",
        "google.generativeai",
        "ollama",
        "socket",
        "urllib.request",
        "http.client",
    }

    src_root = Path("src/flowlens")
    for py_file in src_root.rglob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for banned in banned_modules:
                        assert not alias.name.startswith(banned), (
                            f"Prohibited import '{alias.name}' found in {py_file}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for banned in banned_modules:
                        assert not node.module.startswith(banned), (
                            f"Prohibited from-import '{node.module}' found in {py_file}"
                        )


def test_deskmate_license_in_distribution():
    """DeskMate の MIT ライセンス表示が配布物（LICENSE）に含まれる"""
    license_file = Path("LICENSE")
    assert license_file.exists(), "LICENSE file must exist"

    content = license_file.read_text(encoding="utf-8")
    assert "DeskMate" in content
    assert "https://github.com/zhaohb/deskmate" in content
    assert "zhaohb" in content
    assert "MIT License" in content


def test_uninstaller_data_retention_choice():
    """アンインストールで記録データを消すか残すかを選べ、選んだとおりになる"""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        install_dir = base / "Programs" / "FlowLens"
        data_dir = base / "FlowLens"

        # Case 1: keep_data = True -> data is preserved
        install_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        (install_dir / "flowlens.exe").write_text("binary", encoding="utf-8")
        (data_dir / "collector.db").write_text("sqlite", encoding="utf-8")

        uninstall_app(target_dir=install_dir, data_dir=data_dir, keep_data=True)

        assert not install_dir.exists(), "Installed binaries must be removed"
        assert data_dir.exists(), "Data directory must be kept when keep_data=True"
        assert (data_dir / "collector.db").exists()

        # Case 2: keep_data = False -> data is deleted
        install_dir.mkdir(parents=True, exist_ok=True)
        (install_dir / "flowlens.exe").write_text("binary", encoding="utf-8")

        uninstall_app(target_dir=install_dir, data_dir=data_dir, keep_data=False)

        assert not install_dir.exists()
        assert not data_dir.exists(), "Data directory must be deleted when keep_data=False"
