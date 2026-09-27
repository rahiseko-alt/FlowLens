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
    """Records that (and when) the employee consented. Which past sources were chosen
    is a setting of the Recorder, kept in one place only."""

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.consent_file = self.storage_dir / "consent.json"

    def has_consent(self) -> bool:
        data = self._read_file()
        return bool(data and data.get("consented") is True)

    def get_consent_timestamp(self) -> datetime | None:
        data = self._read_file()
        try:
            return datetime.fromisoformat(data["granted_at"]) if data else None
        except (KeyError, ValueError):
            return None

    def grant_consent(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": CONSENT_VERSION,
            "consented": True,
            "granted_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.consent_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _read_file(self) -> dict[str, Any] | None:
        if not self.consent_file.exists():
            return None
        try:
            with open(self.consent_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None
