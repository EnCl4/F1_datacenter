"""T035 -- the recorder status file the launcher and API poll.

The recorder is headless; this file is how anything else learns what it is doing
(FR-026). Written atomically so a reader never sees a half-written document.

Deliberately carries raw ``track_id`` and ``session_type`` integers rather than names:
resolving them would mean importing the enum tables into the capture package, and the
launcher can map them just as easily.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: A status file older than this is treated as stopped. A crashed recorder must never
#: keep appearing to run (http-api.md).
STALE_AFTER_SECONDS = 10.0

STATE_LISTENING = "listening"
STATE_RECORDING = "recording"
STATE_STOPPED = "stopped"
STATE_ERROR = "error"


@dataclass
class SessionStatus:
    uid: str
    track_id: int
    session_type: int
    current_lap: int
    started_late: bool


@dataclass
class RecorderStatus:
    state: str = STATE_STOPPED
    since: float | None = None
    """Unix timestamp the recorder started listening."""

    session: SessionStatus | None = None
    packets: int = 0
    bytes: int = 0
    loss_pct: float = 0.0
    queue_high_water: int = 0
    free_disk_gb: float = 0.0
    sessions_recorded: int = 0
    message: str | None = None
    updated_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["updated_at"] = time.time()
        return json.dumps(payload, indent=2)


def write_status(path: Path, status: RecorderStatus) -> None:
    """Write atomically: a reader polling at 2 Hz must never see a partial file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(status.to_json(), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # Status reporting must never take the recorder down. Losing a status update is
        # cosmetic; losing the session is not.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def read_status(path: Path, *, stale_after: float = STALE_AFTER_SECONDS) -> dict:
    """Read the status file, reporting ``stopped`` when it is missing or stale."""
    stopped = {
        "state": STATE_STOPPED,
        "recording": False,
        "since": None,
        "session": None,
        "stale": False,
    }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return stopped

    updated_at = raw.get("updated_at") or 0.0
    if time.time() - updated_at > stale_after:
        stopped["stale"] = True
        stopped["last_seen"] = updated_at
        return stopped

    raw["recording"] = raw.get("state") == STATE_RECORDING
    raw["stale"] = False
    return raw


def clear_status(path: Path, message: str | None = None) -> None:
    """Mark the recorder stopped on a clean shutdown."""
    write_status(path, RecorderStatus(state=STATE_STOPPED, message=message))
