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
class TypingObservation(Observation):
    """Observation of typing activity."""

    keystrokes: int = 1
    duration_seconds: float = 0.0
    is_password: bool = False
    raw_text: str = ""  # Input from Windows hook, discarded by core
    app_name: str | None = None
    window_title: str | None = None


@dataclass(frozen=True)
class OperationTypeObservation(Observation):
    """Observation of operational key combination (copy, paste, enter, etc.)."""

    operation_type: str
    app_name: str | None = None


@dataclass(frozen=True)
class ClipboardObservation(Observation):
    """Observation of clipboard operations (copy, cut, paste)."""

    action: str  # "copy", "cut", "paste"
    data_type: str = "text"
    data_length: int = 0
    raw_content: str = ""  # Input from hook, discarded by core
    app_name: str | None = None


@dataclass(frozen=True)
class ControlMetadataObservation(Observation):
    """Observation of UI element interaction or browser navigation."""

    event_type: str = "click"
    control_type: str = ""
    automation_id: str = ""
    class_name: str = ""
    framework_id: str = ""
    state: str = ""
    url: str = ""
    name: str = ""  # Input from hook, discarded by core
    value: str = ""  # Input from hook, discarded by core
    app_name: str | None = None
    window_title: str | None = None


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


@dataclass(frozen=True)
class PastAppUsageObservation:
    """Past foreground app usage from sources like SRUM or UserAssist."""

    app_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    window_title: str = ""
    source: str = "srum"


@dataclass(frozen=True)
class PastSystemEventObservation:
    """Past power or system lifecycle event (boot, shutdown, sleep, resume, logon, lock)."""

    event_type: str
    timestamp: datetime
    source: str = "event_log"


@dataclass(frozen=True)
class PastFileObservation:
    """Past file interaction from Recent files or Jump lists."""

    file_path: str
    timestamp: datetime
    app_name: str = ""
    source: str = "recent_files"


@dataclass(frozen=True)
class PastBrowserObservation:
    """Past browser navigation history from Chrome, Edge, etc."""

    url: str
    timestamp: datetime
    source: str = "chrome_history"

