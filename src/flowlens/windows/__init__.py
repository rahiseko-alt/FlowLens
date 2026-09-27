"""FlowLens Windows integration entry points."""

from flowlens.windows.activity_watcher import WindowsActivityWatcher
from flowlens.windows.app import CollectorApp
from flowlens.windows.autostart import is_autostart_enabled, set_autostart
from flowlens.windows.consent_dialog import ConsentDialog
from flowlens.windows.input_watcher import WindowsInputWatcher
from flowlens.windows.past_import import get_windows_past_providers, run_windows_past_import
from flowlens.windows.status_window import StatusWindow

__all__ = [
    "CollectorApp",
    "ConsentDialog",
    "StatusWindow",
    "WindowsActivityWatcher",
    "WindowsInputWatcher",
    "get_windows_past_providers",
    "is_autostart_enabled",
    "run_windows_past_import",
    "set_autostart",
]
