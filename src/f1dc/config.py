"""T007 -- data directory resolution and cloud-sync-root refusal.

Constitution principle VIII: raw logs and the derived store must never live inside a
cloud-sync directory. Raw capture runs at roughly 1.3 GB/hour at 60 Hz; sync clients
contend for open file handles on an actively-written capture and will upload every byte.
This was not theoretical -- the reference capture recorded a 79-frame gap while writing
into a OneDrive-synced folder.

This module is deliberately standard-library only. The recorder is a leaf package that
may not import it (see tests/contract/test_capture_isolation.py), so the CLI resolves
configuration here and passes concrete paths to the recorder as arguments.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path("C:/F1Data")
DEFAULT_PORT = 20777

#: Free space below which the recorder refuses to start (FR-005). One hour of driving at
#: 60 Hz measures ~1.3 GB, so this is roughly four hours of headroom.
MIN_FREE_BYTES = 5 * 1024**3

#: Free space below which a running recorder warns (FR-005).
WARN_FREE_BYTES = 15 * 1024**3

#: Path fragments that indicate a cloud-sync root. Matched case-insensitively against
#: each path component, so "OneDrive - Contoso" and "My Dropbox" are both caught.
SYNC_ROOT_MARKERS = (
    "onedrive",
    "dropbox",
    "google drive",
    "googledrive",
    "icloud",
    "iclouddrive",
    "box sync",
    "pcloud",
    "mega",
    "nextcloud",
    "owncloud",
    "yandexdisk",
    "creative cloud files",
)

ENV_DATA_DIR = "F1DC_DATA_DIR"
ENV_ALLOW_SYNC = "F1DC_ALLOW_SYNC_ROOT"


class ConfigError(Exception):
    """Configuration is unusable and the caller must not proceed."""


@dataclass(frozen=True)
class Paths:
    """Resolved on-disk locations. All absolute."""

    data_dir: Path

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"

    @property
    def sessions_dir(self) -> Path:
        return self.derived_dir / "sessions"

    @property
    def catalog_path(self) -> Path:
        return self.derived_dir / "catalog.duckdb"

    @property
    def status_path(self) -> Path:
        return self.data_dir / "recorder-status.json"

    def ensure(self) -> None:
        for d in (self.data_dir, self.raw_dir, self.derived_dir, self.sessions_dir):
            d.mkdir(parents=True, exist_ok=True)


def detect_sync_root(path: Path) -> str | None:
    """Return the offending component if *path* sits inside a known cloud-sync tree.

    Checks both the path itself and the environment variables sync clients export,
    because a junction or a relocated OneDrive folder need not contain "OneDrive" in
    its name.
    """
    resolved = path.expanduser().resolve()

    for part in resolved.parts:
        lowered = part.casefold()
        for marker in SYNC_ROOT_MARKERS:
            if marker in lowered:
                return part

    for env_name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            sync_root = Path(raw).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if resolved == sync_root or sync_root in resolved.parents:
            return f"{env_name}={sync_root}"

    return None


def free_bytes(path: Path) -> int:
    """Free space on the volume containing *path*, walking up to the nearest existing dir."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def resolve_data_dir(explicit: Path | str | None = None, *, allow_sync_root: bool = False) -> Path:
    """Resolve the data directory, refusing a cloud-sync root unless overridden.

    Precedence: explicit argument, then ``F1DC_DATA_DIR``, then ``C:\\F1Data``.

    Raises:
        ConfigError: if the location is inside a sync root and not explicitly allowed.
    """
    if explicit is not None:
        candidate = Path(explicit)
    elif env := os.environ.get(ENV_DATA_DIR):
        candidate = Path(env)
    else:
        candidate = DEFAULT_DATA_DIR

    candidate = candidate.expanduser()
    try:
        candidate = candidate.resolve()
    except OSError as exc:  # pragma: no cover - exercised only on broken mounts
        raise ConfigError(f"cannot resolve data directory {candidate}: {exc}") from exc

    allowed = allow_sync_root or os.environ.get(ENV_ALLOW_SYNC) == "1"
    if not allowed and (offender := detect_sync_root(candidate)):
        raise ConfigError(
            f"data directory {candidate} is inside a cloud-sync folder ({offender}).\n"
            f"Telemetry capture writes ~1.3 GB/hour; a sync client will fight the recorder "
            f"for the open file and upload every byte.\n"
            f"Choose a different location, or set {ENV_ALLOW_SYNC}=1 to override."
        )

    return candidate


def load_paths(explicit: Path | str | None = None, *, allow_sync_root: bool = False) -> Paths:
    """Resolve and create the directory layout."""
    paths = Paths(resolve_data_dir(explicit, allow_sync_root=allow_sync_root))
    try:
        paths.ensure()
    except OSError as exc:
        raise ConfigError(f"data directory {paths.data_dir} is not writable: {exc}") from exc
    return paths
