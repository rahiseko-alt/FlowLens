"""#21 (core part): recording, Past Import and export never touch the network."""

import socket
from pathlib import Path

import pytest
from conftest import at, use

from flowlens.core import (
    ClipboardObservation,
    PastBrowserObservation,
    PastSystemEventObservation,
    WindowObservation,
)

NETWORK_MODULES = {"requests", "httpx", "urllib3", "aiohttp", "websockets", "openai", "anthropic"}


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_full_flow_without_network(no_network, recorder, export):
    recorder.import_past_providers(
        {
            "system_log": lambda: [PastSystemEventObservation("boot", at(-60))],
            "browser_history": lambda: [PastBrowserObservation("a.example", at(-30))],
        }
    )
    recorder.observe(WindowObservation(timestamp=at(0), app_name="chrome.exe"))
    recorder.observe(ClipboardObservation(at(1), "copy", app_name="chrome.exe"))
    recorder.observe(WindowObservation(timestamp=at(2), app_name="excel.exe"))
    recorder.observe(ClipboardObservation(at(3), "paste", app_name="excel.exe"))
    use(recorder, "excel.exe", 3, 4)
    exp = export()
    assert exp.json("manifest.json")["record_counts"]["app_sessions"] == 2


def test_no_network_library_is_imported_or_declared():
    root = Path(__file__).resolve().parents[1]
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (root / "src").rglob("*.py"))
    for name in NETWORK_MODULES | {"socket", "http.client", "urllib.request"}:
        assert f"import {name}" not in sources
        assert f"from {name}" not in sources
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8").lower()
    for name in NETWORK_MODULES:
        assert f'"{name}' not in pyproject
