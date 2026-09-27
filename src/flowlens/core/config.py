from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_RETENTION_DAYS = 30


class ConfigManager:
    """Manages persistent application configuration (excluded apps, retention policy)."""

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.config_path = self.storage_dir / "config.json"
        self._config: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {
                "excluded_apps": [],
                "retention_days": DEFAULT_RETENTION_DAYS,
            }
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
                data.setdefault("excluded_apps", [])
                data.setdefault("retention_days", DEFAULT_RETENTION_DAYS)
                return data
        except (json.JSONDecodeError, OSError):
            return {
                "excluded_apps": [],
                "retention_days": DEFAULT_RETENTION_DAYS,
            }

    def _save(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    def get_excluded_apps(self) -> list[str]:
        """Returns the list of excluded application names."""
        return list(self._config.get("excluded_apps", []))

    def add_excluded_app(self, app_name: str) -> None:
        """Adds an application to the excluded list."""
        clean = app_name.lower().strip()
        if not clean:
            return
        current = set(self._config.get("excluded_apps", []))
        if clean not in current:
            apps = list(self._config.get("excluded_apps", []))
            apps.append(clean)
            self._config["excluded_apps"] = apps
            self._save()

    def remove_excluded_app(self, app_name: str) -> None:
        """Removes an application from the excluded list."""
        clean = app_name.lower().strip()
        current = self._config.get("excluded_apps", [])
        if clean in current:
            self._config["excluded_apps"] = [a for a in current if a != clean]
            self._save()

    def get_retention_days(self) -> int | None:
        """Returns the data retention period in days (None means indefinite)."""
        return self._config.get("retention_days")

    def set_retention_days(self, days: int | None) -> None:
        """Sets the data retention period in days (None or <= 0 means indefinite)."""
        if days is None or days <= 0:
            self._config["retention_days"] = None
        else:
            self._config["retention_days"] = int(days)
        self._save()
