"""HMAC hashing for window titles and machine identification."""

import hashlib
import hmac
import os
import re
import uuid
from pathlib import Path


class KeyManager:
    """Manages the secret key for HMAC hashing and the random machine ID."""

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = self.storage_dir / "secret.key"
        self.machine_id_file = self.storage_dir / "machine_id.txt"
        self._key: bytes | None = None
        self._machine_id: str | None = None

    def get_key(self) -> bytes:
        if self._key is not None:
            return self._key
        if self.key_file.exists():
            self._key = self.key_file.read_bytes()
        else:
            self._key = os.urandom(32)
            self.key_file.write_bytes(self._key)
        return self._key

    def get_machine_id(self) -> str:
        if self._machine_id is not None:
            return self._machine_id
        if self.machine_id_file.exists():
            self._machine_id = self.machine_id_file.read_text(encoding="utf-8").strip()
        else:
            self._machine_id = str(uuid.uuid4())
            self.machine_id_file.write_text(self._machine_id, encoding="utf-8")
        return self._machine_id

    def hash_title(self, title: str | None) -> tuple[str, str]:
        """Returns (keyed_hash, file_extension).

        Never returns or stores the raw title string.
        """
        if not title:
            return "", ""

        # Extract file extension if present (e.g., .xlsx, .docx, .py, etc.)
        # Match dot followed by 1-5 alphanumeric characters before word boundary or end of title
        ext = ""
        match = re.search(r"\.([a-zA-Z0-9]{1,5})(?:\s|[-–—_]|$)", title)
        if match:
            ext = f".{match.group(1).lower()}"

        key = self.get_key()
        h = hmac.new(key, title.encode("utf-8", errors="replace"), hashlib.sha256)
        hashed_title = h.hexdigest()[:16]
        return hashed_title, ext
