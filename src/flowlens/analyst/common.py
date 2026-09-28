"""Small helpers shared by the summary and the candidate finders."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, tzinfo
from typing import Any

from flowlens.analyst.reader import OpenedExport


def local(value: str, tz: tzinfo) -> datetime:
    """A stored UTC time string, in the customer's time zone."""
    return datetime.fromisoformat(value).astimezone(tz)


def rows(exports: list[OpenedExport], sql: str) -> Iterator[Any]:
    """The rows of one query, across every export."""
    for export in exports:
        yield from export.db.execute(sql)
