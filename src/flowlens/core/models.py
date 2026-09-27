"""Core data models and observations for FlowLens."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeRange:
    """Represents a time range for queries, retention, and export."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class Observation:
    """Base class for all observations."""

    timestamp: datetime


@dataclass(frozen=True)
class WindowObservation(Observation):
    """Observation of active window focus."""

    app_name: str
    window_title: str = ""
    process_id: int | None = None
    exe_path: str | None = None


@dataclass(frozen=True)
class IdleObservation(Observation):
    """Observation of user idle state."""

    is_idle: bool


@dataclass(frozen=True)
class LockObservation(Observation):
    """Observation of workstation lock state."""

    is_locked: bool


@dataclass(frozen=True)
class SleepObservation(Observation):
    """Observation of system sleep/suspend state."""

    is_asleep: bool


@dataclass(frozen=True)
class SessionDisconnectObservation(Observation):
    """Observation of terminal/session disconnect state."""

    is_disconnected: bool


@dataclass(frozen=True)
class AppSession:
    """An app session representing uninterrupted active foreground usage."""

    app_name: str
    window_title_hash: str
    window_title_ext: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    is_past: int = 0
    source: str = "live"
