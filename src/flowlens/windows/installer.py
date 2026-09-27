from __future__ import annotations

import os
import shutil
from pathlib import Path

from flowlens.windows.autostart import set_autostart


def get_default_install_dir() -> Path:
    """Returns the default per-user application installation directory."""
    localappdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "."
    return Path(localappdata) / "Programs" / "FlowLens"


def get_default_data_dir() -> Path:
    """Returns the default per-user data directory."""
    localappdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "."
    return Path(localappdata) / "FlowLens"


def get_start_menu_shortcut_path() -> Path | None:
    """Returns the Start Menu shortcut path for current user."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "FlowLens.lnk"


def install_app(
    source_dir: str | Path,
    target_dir: str | Path | None = None,
    enable_autostart: bool = True,
) -> Path:
    """Installs FlowLens Collector to the target directory, sets up autostart."""
    src = Path(source_dir)
    dest = Path(target_dir) if target_dir else get_default_install_dir()
    dest.mkdir(parents=True, exist_ok=True)

    # Copy files
    for item in src.iterdir():
        target_item = dest / item.name
        if item.is_dir():
            if target_item.exists():
                shutil.rmtree(target_item)
            shutil.copytree(item, target_item)
        else:
            shutil.copy2(item, target_item)

    # Configure autostart
    exe_path = dest / "flowlens.exe"
    if enable_autostart:
        set_autostart("FlowLens", f'"{exe_path}"', enable=True)

    return dest


def uninstall_app(
    target_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    keep_data: bool = True,
) -> bool:
    """Uninstalls FlowLens Collector.

    If keep_data is False, deletes all collected data in data_dir.
    If keep_data is True, preserves data_dir.
    """
    dest = Path(target_dir) if target_dir else get_default_install_dir()
    data = Path(data_dir) if data_dir else get_default_data_dir()

    # Disable autostart
    set_autostart("FlowLens", "", enable=False)

    # Remove Start Menu shortcut
    shortcut = get_start_menu_shortcut_path()
    if shortcut and shortcut.exists():
        try:
            shortcut.unlink()
        except OSError:
            pass

    # Remove installed files
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    # Handle data directory
    if not keep_data and data.exists():
        shutil.rmtree(data, ignore_errors=True)

    return True
