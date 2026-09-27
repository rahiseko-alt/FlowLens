"""FlowLens Windows integration entry points."""

from flowlens.windows.app import CollectorApp
from flowlens.windows.autostart import is_autostart_enabled, set_autostart
from flowlens.windows.consent_dialog import ConsentDialog
from flowlens.windows.input_watcher import WindowsInputWatcher
from flowlens.windows.installer import install_app, uninstall_app
from flowlens.windows.past_import import get_windows_past_providers, run_windows_past_import
from flowlens.windows.settings_window import SettingsWindow
from flowlens.windows.status_window import StatusWindow
from flowlens.windows.watcher import WindowsActivityWatcher

__all__ = [
    "CollectorApp",
    "ConsentDialog",
    "SettingsWindow",
    "StatusWindow",
    "WindowsActivityWatcher",
    "WindowsInputWatcher",
    "get_windows_past_providers",
    "install_app",
    "is_autostart_enabled",
    "run_windows_past_import",
    "set_autostart",
    "uninstall_app",
]
