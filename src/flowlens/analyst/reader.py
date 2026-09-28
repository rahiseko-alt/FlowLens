"""Opens Diagnostic Exports and checks they are ones this analyst can read."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyzipper

SUPPORTED_SCHEMA_VERSIONS = {2}
REQUIRED_MEMBERS = ("data.sqlite", "manifest.json", "redaction_report.json")


class ExportError(Exception):
    """A file that cannot be analysed; the message is for the consultant."""

    def __init__(self, path: Path, reason: str):
        super().__init__(f"{path.name}: {reason}")


@dataclass
class OpenedExport:
    manifest: dict[str, Any]
    redaction: dict[str, Any]
    db: sqlite3.Connection


def open_export(path: Path, password: str, work_dir: Path) -> OpenedExport:
    """Decrypts `path` into `work_dir` (which the caller deletes afterwards)."""
    try:
        with pyzipper.AESZipFile(path) as zf:
            zf.setpassword(password.encode("utf-8"))
            names = set(zf.namelist())
            if not set(REQUIRED_MEMBERS) <= names:
                raise ExportError(path, "FlowLens の書き出しではありません")
            members = {name: zf.read(name) for name in REQUIRED_MEMBERS}
    except ExportError:
        raise
    except RuntimeError as exc:  # pyzipper: "Bad password for file"
        raise ExportError(path, "パスワードが違います") from exc
    except (pyzipper.BadZipFile, zipfile.BadZipFile, OSError, EOFError) as exc:
        raise ExportError(path, "ファイルが壊れているか、ZIP ではありません") from exc

    try:
        manifest = json.loads(members["manifest.json"])
        redaction = json.loads(members["redaction_report.json"])
    except ValueError as exc:
        raise ExportError(path, "FlowLens の書き出しではありません") from exc
    version = manifest.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ExportError(path, f"対応していない版です（schema_version={version}）")

    db_path = work_dir / f"{len(list(work_dir.iterdir()))}.sqlite"
    db_path.write_bytes(members["data.sqlite"])
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return OpenedExport(manifest, redaction, db)
