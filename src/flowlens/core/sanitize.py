"""Rules that decide what may be stored (ADR 0002, 0003).

Every value that reaches storage or the Diagnostic Export passes through one of
these functions. Each function returns a safe value or an empty string; none of
them ever returns the input unchanged unless it matched a narrow, content-free shape.
"""

import re
import urllib.parse

# Extensions we are willing to keep next to a hashed title or file name.
# An allowlist, so that "Re: call John.Smith - Outlook" does not leak ".smith".
FILE_EXTENSIONS = frozenset(
    """
    xlsx xlsm xlsb xls csv tsv docx docm doc rtf odt ods odp pptx pptm ppt pdf txt md
    msg eml ics vsdx vsd one accdb mdb pub xps oxps
    png jpg jpeg gif bmp tif tiff svg heic webp
    zip 7z rar lzh
    xml json yaml yml html htm css js ts py ps1 bat cmd sql log ini cfg conf
    mp3 mp4 wav mov avi wmv
    """.split()
)

_EXT_RE = re.compile(r"\.([A-Za-z0-9]{1,5})(?=$|[\s\]\)\-–—|:*」』）】])")
_EXE_RE = re.compile(r"^[a-z0-9][a-z0-9 ._()+-]{0,79}\.exe$")
# Packaged (UWP) app ids, e.g. Microsoft.WindowsCalculator_8wekyb3d8bbwe!App
_AUMID_RE = re.compile(r"^[a-z0-9.]{3,80}_[a-z0-9]{13}![a-z0-9._]{1,40}$")
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:\-]{0,63}$")

OPERATION_TYPES = frozenset({"ctrl+c", "ctrl+x", "ctrl+v", "enter", "tab", "escape", "shortcut"})
CLIPBOARD_ACTIONS = frozenset({"copy", "cut", "paste"})
CLIPBOARD_DATA_TYPES = frozenset({"text", "files", "image", "other"})
CONTROL_EVENT_TYPES = frozenset({"click", "focus", "navigate"})
CONTROL_STATES = frozenset({"", "on", "off", "indeterminate", "expanded", "collapsed", "selected"})
SYSTEM_EVENT_TYPES = frozenset(
    {"boot", "shutdown", "sleep", "resume", "logon", "logoff", "lock", "unlock"}
)


def file_extension(name: str | None) -> str:
    """Returns the last allowlisted extension found in `name` (".xlsx"), or ""."""
    if not name or not isinstance(name, str):
        return ""
    found = ""
    for match in _EXT_RE.finditer(name):
        ext = match.group(1).lower()
        if ext in FILE_EXTENSIONS:
            found = f".{ext}"
    return found


def app_name(raw: str | None) -> tuple[str, bool]:
    """Normalises an app name to a lowercase executable or packaged-app id.

    Returns (name, ok). When `ok` is False the value did not look like an app at
    all (it may be a document name) and must not be stored as-is.
    """
    if not raw or not isinstance(raw, str):
        return "", bool(not raw)
    base = re.split(r"[\\/]", raw.strip())[-1].strip().lower()
    if _EXE_RE.match(base) or _AUMID_RE.match(base):
        return base, True
    return "", False


def domain(raw: str | None) -> str:
    """Reduces a host name or URL to a lowercase host. Anything else becomes ""."""
    if not raw or not isinstance(raw, str):
        return ""
    value = raw.strip()
    if "://" in value:
        try:
            parts = urllib.parse.urlsplit(value)
        except ValueError:
            return ""
        if parts.scheme.lower() not in ("http", "https"):
            return ""
        value = parts.hostname or ""
    else:
        value = re.split(r"[/?#]", value, maxsplit=1)[0]
        value = value.rsplit("@", 1)[-1].split(":", 1)[0]
    value = value.lower().rstrip(".")
    return value if _HOST_RE.match(value) else ""


def identifier(raw: str | None) -> str:
    """Keeps UI identifiers (AutomationId, ClassName, ...) only if they look like code names.

    Web pages sometimes put user content into automation ids; those contain
    spaces or other characters and are dropped.
    """
    if not raw or not isinstance(raw, str):
        return ""
    value = raw.strip()
    return value if _IDENT_RE.match(value) else ""


def choice(raw: str | None, allowed: frozenset[str], default: str = "") -> str:
    value = raw.strip().lower() if isinstance(raw, str) else ""
    return value if value in allowed else default


_ERROR_RE = re.compile(r"^[A-Za-z0-9_ .:-]{1,80}$")


def error_code(raw: str | None) -> str:
    """Keeps a failure reason only if it is a short code (no paths, no messages)."""
    value = raw.strip() if isinstance(raw, str) else ""
    return value if _ERROR_RE.match(value) and "\\" not in value and "/" not in value else ""
