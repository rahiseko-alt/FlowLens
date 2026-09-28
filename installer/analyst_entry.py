"""Entry point PyInstaller builds into flowlens_analyst.exe."""

import sys

from flowlens.analyst.app import run

sys.exit(run())
