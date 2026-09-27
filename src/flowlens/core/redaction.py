"""Redaction utilities for FlowLens Core."""

import urllib.parse


def extract_browser_domain(url: str | None) -> str:
    """Extracts only the domain/host from an HTTP/HTTPS URL.

    Paths, query parameters, fragments, tokens, and non-http schemes are removed.
    """
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return ""
        host = parsed.hostname
        return (host or "").lower()
    except Exception:
        return ""
