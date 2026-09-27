"""`python -m flowlens` and the packaged flowlens.exe start the Windows Collector."""

import sys

from flowlens.windows.app import main

if __name__ == "__main__":
    sys.exit(main())
