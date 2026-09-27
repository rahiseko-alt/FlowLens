from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_RETENTION_DAYS = 30
DEFAULT_IDLE_THRESHOLD_SECONDS = 300.0
DEFAULTS_VERSION = 2  # raise when new defaults must reach existing settings


# Password managers are excluded from the start: copying a password from one would
# otherwise leave at least its length in a Clipboard Transfer.
DEFAULT_EXCLUDED_APPS = [
    "1password.exe",
    "bitwarden.exe",
    "dashlane.exe",
    "keepass.exe",
    "keepassxc.exe",
    "lastpass.exe",
    "nordpass.exe",
]


def _defaults() -> dict[str, Any]:
    return {
        "excluded_apps": list(DEFAULT_EXCLUDED_APPS),
        "retention_days": DEFAULT_RETENTION_DAYS,
        "idle_threshold_seconds": DEFAULT_IDLE_THRESHOLD_SECONDS,
        "paused_since": None,
        "user_exited": False,
        "enabled_past_sources": None,
    }


class ConfigManager:
    """Persistent settings: exclusions, retention, idle threshold, pause state, past sources."""

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.config_path = self.storage_dir / "config.json"
        self._config: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        config = _defaults()
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    config.update(data)
            except (json.JSONDecodeError, OSError):
                pass
        if config.get("defaults_version", 0) < DEFAULTS_VERSION:
            # Settings saved by an older version get the newer default exclusions once.
            config["excluded_apps"] = sorted(
                set(config["excluded_apps"]) | set(DEFAULT_EXCLUDED_APPS)
            )
            config["defaults_version"] = DEFAULTS_VERSION
        return config

    def _save(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)
        tmp.replace(self.config_path)

    def get(self, key: str) -> Any:
        return self._config.get(key)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._save()
