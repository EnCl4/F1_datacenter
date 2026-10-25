"""T007 -- the write lock shared by ingest and session deletion (FR-031, research R7).

Constitution 1.1.0 added a second writer to the derived store: deleting a session. The two
must never interleave. A deletion during an ingest could otherwise remove a directory
ingest is about to rename into place, or the reverse.

The lock is a file created exclusively, which is atomic on every filesystem this runs on.
A lock older than an hour is treated as stale (a crashed ingest), and long runs refresh it.

Liveness is deliberately never checked with ``os.kill(pid, 0)``. On POSIX that is a
harmless probe; **on Windows, ``os.kill`` with any signal other than CTRL_C/CTRL_BREAK
calls TerminateProcess** -- it would kill the very ingest it was asking about.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from f1dc.config import Paths

LOCK_NAME = ".write.lock"
STALE_AFTER_SECONDS = 3600


class WriteLockBusy(Exception):
    """Another writer holds the lock."""

    def __init__(self, holder: str) -> None:
        super().__init__(holder)
        self.holder = holder


@dataclass
class WriteLock:
    path: Path

    def refresh(self) -> None:
        """Keep a long-running holder from looking stale."""
        try:
            os.utime(self.path)
        except OSError:
            pass


def lock_path(paths: Paths) -> Path:
    return paths.derived_dir / LOCK_NAME


def _describe(path: Path) -> str:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        return f"{info.get('owner', 'another process')} (since {time.ctime(info.get('since', 0))})"
    except (OSError, ValueError):
        return "another process"


def _create(path: Path) -> int:
    return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)


@contextmanager
def write_lock(paths: Paths, owner: str) -> Iterator[WriteLock]:
    """Hold the derived store's write lock for the duration of the block.

    Raises:
        WriteLockBusy: another writer holds a fresh lock.
    """
    path = lock_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd = _create(path)
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            age = STALE_AFTER_SECONDS + 1  # released between our two calls
        if age < STALE_AFTER_SECONDS:
            raise WriteLockBusy(_describe(path)) from None
        path.unlink(missing_ok=True)  # stale: its holder is gone
        try:
            fd = _create(path)
        except FileExistsError:
            raise WriteLockBusy(_describe(path)) from None

    try:
        os.write(fd, json.dumps({"owner": owner, "pid": os.getpid(), "since": time.time()}).encode())
    finally:
        os.close(fd)

    try:
        yield WriteLock(path)
    finally:
        path.unlink(missing_ok=True)
