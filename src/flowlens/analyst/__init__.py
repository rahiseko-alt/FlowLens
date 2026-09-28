"""Analyst side: Diagnostic Exports in, an Analysis Summary out (ADR 0006).

Runs on the consultant's PC. It depends only on the shape of the export
(data.sqlite, manifest.json, redaction_report.json), never on the Collector's
code, and sends nothing anywhere.
"""

from flowlens.analyst.cli import main

__all__ = ["main"]
