from __future__ import annotations

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(app_name: str, command: str, enable: bool = True) -> bool:
    """Configures whether the app starts automatically on user login via HKCU Run key."""
    if winreg is None:
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        ) as key:
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def is_autostart_enabled(app_name: str) -> bool:
    """Checks if the app is currently configured to start automatically on login."""
    if winreg is None:
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            winreg.KEY_QUERY_VALUE,
        ) as key:
            try:
                winreg.QueryValueEx(key, app_name)
                return True
            except FileNotFoundError:
                return False
    except OSError:
        return False
