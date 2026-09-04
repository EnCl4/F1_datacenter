"""T054 -- where derived data lives on disk.

One directory per session. That is what makes idempotence structural rather than a matter
of careful transaction handling: re-ingesting a session rewrites its directory and touches
nothing else, and rebuilding the whole store is a delete plus a re-run.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from f1dc.config import Paths

SESSION_FILE = "session.parquet"
LAPS_FILE = "laps.parquet"
STINTS_FILE = "stints.parquet"
RECORDINGS_FILE = "recordings.parquet"
STARRED_FILE = "starred.json"


def session_dir(paths: Paths, session_uid: str) -> Path:
    return paths.sessions_dir / session_uid


def temp_session_dir(paths: Paths, session_uid: str) -> Path:
    """Written first, then renamed into place, so a failed run leaves nothing half-done."""
    return paths.sessions_dir / f".{session_uid}.tmp"


def session_parquet(paths: Paths, session_uid: str) -> Path:
    return session_dir(paths, session_uid) / SESSION_FILE


def laps_parquet(paths: Paths, session_uid: str) -> Path:
    return session_dir(paths, session_uid) / LAPS_FILE


def stints_parquet(paths: Paths, session_uid: str) -> Path:
    return session_dir(paths, session_uid) / STINTS_FILE


def recordings_parquet(paths: Paths) -> Path:
    return paths.derived_dir / RECORDINGS_FILE


def starred_path(paths: Paths) -> Path:
    """User state, not derived output. Ingest never writes it."""
    return paths.derived_dir / STARRED_FILE


def iter_session_dirs(paths: Paths) -> Iterator[Path]:
    if not paths.sessions_dir.exists():
        return
    for entry in sorted(paths.sessions_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            yield entry


def ingested_session_uids(paths: Paths) -> set[str]:
    return {d.name for d in iter_session_dirs(paths) if (d / SESSION_FILE).exists()}


def raw_logs(paths: Paths) -> list[Path]:
    """Every raw log, compressed or not, oldest first."""
    if not paths.raw_dir.exists():
        return []
    logs = [
        p
        for p in paths.raw_dir.iterdir()
        if p.is_file() and (p.suffix == ".f1raw" or p.name.endswith(".f1raw.zst"))
    ]
    return sorted(logs, key=lambda p: p.name)


def session_glob(paths: Paths, filename: str) -> str:
    """A glob DuckDB can read, with forward slashes even on Windows."""
    return (paths.sessions_dir / "*" / filename).as_posix()
