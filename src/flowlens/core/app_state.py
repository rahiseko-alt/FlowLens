from __future__ import annotations

import os
from pathlib import Path
from typing import IO


class AlreadyRunningError(Exception):
    """Raised when another instance of FlowLens is already running."""


class SingleInstanceLock:
    """Cross-platform single-instance file lock."""

    def __init__(self, storage_dir: str | Path, lock_name: str = "flowlens.lock"):
        self.lock_path = Path(storage_dir) / lock_name
        self._file: IO[bytes] | None = None

    def acquire(self) -> bool:
        """Acquires the single-instance lock or raises AlreadyRunningError."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file = open(self.lock_path, "wb")
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as e:
                    self._file.close()
                    self._file = None
                    raise AlreadyRunningError("Another instance of FlowLens is running") from e
            else:
                import fcntl

                try:
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as e:
                    self._file.close()
                    self._file = None
                    raise AlreadyRunningError("Another instance of FlowLens is running") from e

            # Write current PID to lock file
            self._file.write(str(os.getpid()).encode("ascii"))
            self._file.flush()
            return True
        except (OSError, PermissionError) as e:
            if self._file:
                try:
                    self._file.close()
                except OSError:
                    pass
                self._file = None
            raise AlreadyRunningError("Another instance of FlowLens is running") from e

    def release(self) -> None:
        """Releases the lock."""
        if self._file:
            try:
                if os.name == "nt":
                    import msvcrt

                    try:
                        self._file.seek(0)
                        msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl

                    try:
                        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
                self._file.close()
            except OSError:
                pass
            finally:
                self._file = None

        if self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                pass

    def __enter__(self) -> SingleInstanceLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
