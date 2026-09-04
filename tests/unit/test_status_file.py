"""T029 -- the recorder status file.

Shape per contracts/cli.md. Two properties matter beyond the schema: writes are atomic,
because the launcher polls at 2 Hz and must never read a half-written file; and a stale
file reads as stopped, because a crashed recorder must never appear to be running
(FR-029).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from f1dc.capture.status import (
    STALE_AFTER_SECONDS,
    STATE_LISTENING,
    STATE_RECORDING,
    STATE_STOPPED,
    RecorderStatus,
    SessionStatus,
    clear_status,
    read_status,
    write_status,
)


def test_listening_status_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    write_status(path, RecorderStatus(state=STATE_LISTENING, since=time.time(), free_disk_gb=412.6))

    status = read_status(path)
    assert status["state"] == STATE_LISTENING
    assert status["recording"] is False
    assert status["session"] is None
    assert status["free_disk_gb"] == 412.6


def test_recording_status_carries_the_session(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    write_status(
        path,
        RecorderStatus(
            state=STATE_RECORDING,
            since=time.time(),
            session=SessionStatus(
                uid="15975277775803518192",
                track_id=16,
                session_type=10,
                current_lap=3,
                started_late=False,
            ),
            packets=182451,
            bytes=231666957,
            loss_pct=0.205,
        ),
    )

    status = read_status(path)
    assert status["recording"] is True
    session = status["session"]
    assert session["uid"] == "15975277775803518192"
    assert session["track_id"] == 16
    assert session["session_type"] == 10
    assert session["current_lap"] == 3
    assert status["loss_pct"] == 0.205


def test_status_carries_raw_ids_not_names(tmp_path: Path) -> None:
    """Resolving names would mean importing enum tables into the capture package."""
    path = tmp_path / "status.json"
    write_status(
        path,
        RecorderStatus(
            state=STATE_RECORDING,
            session=SessionStatus("1", track_id=16, session_type=10, current_lap=1,
                                  started_late=False),
        ),
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "track_name" not in raw["session"]
    assert raw["session"]["track_id"] == 16


def test_a_missing_file_reads_as_stopped(tmp_path: Path) -> None:
    assert read_status(tmp_path / "nope.json")["state"] == STATE_STOPPED


def test_a_corrupt_file_reads_as_stopped(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_text("{not json at all", encoding="utf-8")
    assert read_status(path)["state"] == STATE_STOPPED


def test_a_stale_file_reads_as_stopped(tmp_path: Path) -> None:
    """A killed recorder leaves its last status behind; it must not look alive (FR-029)."""
    path = tmp_path / "status.json"
    write_status(path, RecorderStatus(state=STATE_RECORDING))

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["updated_at"] = time.time() - (STALE_AFTER_SECONDS + 5)
    path.write_text(json.dumps(raw), encoding="utf-8")

    status = read_status(path)
    assert status["state"] == STATE_STOPPED
    assert status["recording"] is False
    assert status["stale"] is True


def test_a_fresh_file_is_not_stale(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    write_status(path, RecorderStatus(state=STATE_RECORDING))
    assert read_status(path)["stale"] is False


def test_writes_leave_no_temporary_file_behind(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    for _ in range(5):
        write_status(path, RecorderStatus(state=STATE_LISTENING))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["status.json"]


def test_clear_status_marks_stopped(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    write_status(path, RecorderStatus(state=STATE_RECORDING))
    clear_status(path, message="shut down cleanly")
    status = read_status(path)
    assert status["state"] == STATE_STOPPED
    assert status["message"] == "shut down cleanly"


def test_writing_to_an_unwritable_path_does_not_raise(tmp_path: Path) -> None:
    """Status reporting is cosmetic; it must never take the recorder down."""
    write_status(tmp_path / "no" / "such" / "dir" / "s.json", RecorderStatus())
