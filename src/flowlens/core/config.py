from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_RETENTION_DAYS = 30
DEFAULT_IDLE_THRESHOLD_SECONDS = 300.0


def _defaults() -> dict[str, Any]:
    return {
        "excluded_apps": [],
        "retention_days": DEFAULT_RETENTION_DAYS,
        "idle_threshold_seconds": DEFAULT_IDLE_THRESHOLD_SECONDS,
        "paused_since": None,
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
