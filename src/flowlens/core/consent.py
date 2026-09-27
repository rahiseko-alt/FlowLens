from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALL_PAST_SOURCES = [
    "system_log",
    "security_log",
    "user_assist",
    "recent_files",
    "office_recent",
    "browser_history",
]

CONSENT_VERSION = "1.0.0"


class ConsentManager:
    """Manages employee consent for Live Capture and Past Import."""

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.consent_file = self.storage_dir / "consent.json"

    def has_consent(self) -> bool:
        """Returns True if valid consent has been granted."""
        data = self._read_file()
        return bool(data and data.get("consented") is True)

    def get_enabled_sources(self) -> list[str]:
        """Returns the list of enabled past sources.

        Default to all sources if not yet consented.
        """
        data = self._read_file()
        if data and "enabled_sources" in data:
            return list(data["enabled_sources"])
        return list(ALL_PAST_SOURCES)

    def get_consent_timestamp(self) -> datetime | None:
        """Returns the datetime when consent was granted, or None."""
        data = self._read_file()
        if data and data.get("granted_at"):
            try:
                return datetime.fromisoformat(data["granted_at"])
            except ValueError:
                return None
        return None

    def grant_consent(self, enabled_sources: list[str]) -> None:
        """Records consent with the chosen past data sources."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "version": CONSENT_VERSION,
            "consented": True,
            "granted_at": now.isoformat(),
            "enabled_sources": list(enabled_sources),
        }
        with open(self.consent_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def revoke_consent(self) -> None:
        """Revokes consent."""
        if self.consent_file.exists():
            self.consent_file.unlink()

    def _read_file(self) -> dict[str, Any] | None:
        if not self.consent_file.exists():
            return None
        try:
            with open(self.consent_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
