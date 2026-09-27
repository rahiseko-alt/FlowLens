"""FlowLens Windows integration entry points."""

from flowlens.windows.input_watcher import WindowsInputWatcher
from flowlens.windows.past_import import get_windows_past_providers, run_windows_past_import
from flowlens.windows.watcher import WindowsActivityWatcher

__all__ = [
    "WindowsActivityWatcher",
    "WindowsInputWatcher",
    "get_windows_past_providers",
    "run_windows_past_import",
]
