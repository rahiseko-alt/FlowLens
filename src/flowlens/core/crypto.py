"""The PC-local secret key and the random device id (ADR 0003)."""

import hashlib
import hmac
import os
import uuid
from pathlib import Path


class KeyManager:
    """Owns the HMAC key used to turn titles and file names into unreadable symbols.

    The key never leaves the Client PC: it is not part of the Diagnostic Export,
    so nobody holding the export can guess a title by hashing candidates.
    """

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = self.storage_dir / "secret.key"
        self.device_id_file = self.storage_dir / "device_id.txt"
        self._key: bytes | None = None
        self._device_id: str | None = None

    def get_key(self) -> bytes:
        if self._key is None:
            if self.key_file.exists():
                self._key = self.key_file.read_bytes()
            else:
                self._key = os.urandom(32)
                self.key_file.write_bytes(self._key)
        return self._key

    def get_device_id(self) -> str:
        """A random UUID made once per PC. Never derived from the PC or user name."""
        if self._device_id is None:
            if self.device_id_file.exists():
                self._device_id = self.device_id_file.read_text(encoding="utf-8").strip()
            else:
                self._device_id = str(uuid.uuid4())
                self.device_id_file.write_text(self._device_id, encoding="utf-8")
        return self._device_id

    def symbol(self, text: str | None) -> str:
        """A keyed hash of `text` (16 hex characters, 64 bits), or "" for empty text.

        Equal texts give equal symbols, so repeated work on the same file or screen
        stays visible to the analyst without revealing the text itself.
        """
        if not text:
            return ""
        digest = hmac.new(self.get_key(), text.encode("utf-8", "replace"), hashlib.sha256)
        return digest.hexdigest()[:16]
