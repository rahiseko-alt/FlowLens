"""FlowLens Windows integration entry points."""

from flowlens.windows.input_watcher import WindowsInputWatcher
from flowlens.windows.watcher import WindowsActivityWatcher

__all__ = ["WindowsActivityWatcher", "WindowsInputWatcher"]
