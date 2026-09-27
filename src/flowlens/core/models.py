"""Core data models and observations for FlowLens.

Observations carry only what the core is allowed to see. Fields that could hold
user content (typed text, clipboard text, UI Name/Value, full URLs) do not exist,
so the Windows entry points have nowhere to put them (ADR 0002).
The one raw string that does reach the core is the window title, which the core
replaces with a keyed hash before anything is stored (ADR 0003).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeRange:
    """A time range for deletion and export."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class Observation:
    """Base class for all Live Capture observations."""

    timestamp: datetime


@dataclass(frozen=True)
class WindowObservation(Observation):
    """The foreground window at `timestamp`."""

    app_name: str
    window_title: str = ""


@dataclass(frozen=True)
class IdleObservation(Observation):
    """Idle started (`is_idle=True`, timestamp = the last input) or ended."""

    is_idle: bool


@dataclass(frozen=True)
class LockObservation(Observation):
    is_locked: bool


@dataclass(frozen=True)
class SleepObservation(Observation):
    is_asleep: bool


@dataclass(frozen=True)
class SessionDisconnectObservation(Observation):
    is_disconnected: bool


@dataclass(frozen=True)
class TypingObservation(Observation):
    """A burst of typing: how many keys and for how long. Never which keys."""

    keystrokes: int = 1
    duration_seconds: float = 0.0
    is_password: bool = False
    app_name: str | None = None


@dataclass(frozen=True)
class OperationTypeObservation(Observation):
    """An operation key: ctrl+c, ctrl+x, ctrl+v, enter, tab, escape or shortcut."""

    operation_type: str
    app_name: str | None = None
    in_password: bool = False  # pressed while a password box had the focus


@dataclass(frozen=True)
class ClipboardObservation(Observation):
    """A clipboard change (copy/cut) or a paste. Only the kind and size of the data."""

    action: str
    data_type: str = "text"
    data_length: int = 0
    app_name: str | None = None
    in_password: bool = False  # a paste into a password box


@dataclass(frozen=True)
class ControlMetadataObservation(Observation):
    """A clicked or focused UI element, described by metadata only.

    `browser_domain` is a host name the entry point has already cut down from the
    address bar; the core validates it again and drops anything that is not a host.
    """

    event_type: str = "click"
    control_type: str = ""
    automation_id: str = ""
    class_name: str = ""
    framework_id: str = ""
    state: str = ""
    browser_domain: str = ""
    app_name: str | None = None


@dataclass(frozen=True)
class PastAppStatsObservation:
    """Lifetime usage counters of one app kept by Windows (e.g. UserAssist)."""

    app_name: str
    last_used: datetime
    run_count: int = 0
    focus_seconds: float = 0.0
    source: str = "user_assist"


@dataclass(frozen=True)
class PastSystemEventObservation:
    """Past power or session event: boot, shutdown, sleep, resume, logon, logoff, lock, unlock."""

    event_type: str
    timestamp: datetime
    source: str = "system_log"


@dataclass(frozen=True)
class PastFileObservation:
    """A file opened in the past. The core keeps only a keyed hash and the extension."""

    file_name: str
    timestamp: datetime
    app_name: str = ""
    source: str = "recent_files"


@dataclass(frozen=True)
class PastBrowserObservation:
    """One past page visit, already reduced to its host name by the entry point."""

    domain: str
    timestamp: datetime
    app_name: str = ""
    source: str = "browser_history"
