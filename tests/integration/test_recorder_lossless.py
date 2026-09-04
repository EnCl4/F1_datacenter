"""T028 -- the recorder loses nothing.

Replays real captured datagrams over a real UDP socket into a live recorder and asserts
the raw log is byte-identical to what was sent. This is the property everything else in
the product rests on: the game broadcasts once, and whatever the recorder fails to write
is gone permanently.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from f1dc.capture.rawlog import Record, iter_records
from f1dc.capture.recorder import EXIT_PORT_IN_USE, Recorder
from f1dc.capture.status import STATE_STOPPED, read_status
from f1dc.wire.header import decode_header


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_recorder(recorder: Recorder) -> threading.Thread:
    result: list = []
    thread = threading.Thread(target=lambda: result.append(recorder.run()), daemon=True)
    thread.start()
    recorder.result_holder = result  # type: ignore[attr-defined]
    return thread


def wait_until(predicate, timeout: float = 10.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def replay(port: int, payloads: list[bytes], *, chunk: int = 100, pause: float = 0.004) -> None:
    """Send datagrams to the recorder, pacing slightly so loopback buffers keep up."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        for i, payload in enumerate(payloads):
            sender.sendto(payload, ("127.0.0.1", port))
            if i % chunk == chunk - 1:
                time.sleep(pause)


@pytest.fixture
def replay_payloads(records: list[Record]) -> list[bytes]:
    """Every real-session datagram from the fixture, in capture order."""
    return [r.payload for r in records if not decode_header(r.payload).is_menu_state]


def test_recorder_writes_every_datagram_byte_for_byte(
    tmp_path: Path, replay_payloads: list[bytes]
) -> None:
    port = free_port()
    recorder = Recorder(tmp_path / "raw", tmp_path / "status.json", port=port, host="127.0.0.1")
    thread = run_recorder(recorder)

    assert wait_until(lambda: recorder._sock is not None), "recorder never bound its socket"

    replay(port, replay_payloads)
    assert wait_until(lambda: recorder.total_packets >= len(replay_payloads), timeout=20), (
        f"recorder saw {recorder.total_packets} of {len(replay_payloads)} datagrams"
    )

    recorder.stop()
    thread.join(timeout=15)

    logs = sorted((tmp_path / "raw").glob("*.f1raw"))
    assert len(logs) == 1, f"expected one session file, got {[p.name for p in logs]}"

    written = [r.payload for r in iter_records(logs[0])]
    assert written == replay_payloads, "the raw log is not byte-identical to what was sent"
    assert recorder.dropped_by_backpressure == 0


def test_a_new_session_uid_starts_a_new_file(tmp_path: Path, replay_payloads: list[bytes]) -> None:
    """Two sessions in one sitting must not be merged (FR-028, User Story 1 scenario 2)."""
    first = replay_payloads[:400]
    # Forge a second session by rewriting the sessionUID field (bytes 7..15).
    second = [p[:7] + (12345678901234567890).to_bytes(8, "little") + p[15:] for p in first]

    port = free_port()
    recorder = Recorder(tmp_path / "raw", tmp_path / "status.json", port=port, host="127.0.0.1")
    thread = run_recorder(recorder)
    assert wait_until(lambda: recorder._sock is not None)

    replay(port, first + second)
    assert wait_until(lambda: recorder.total_packets >= len(first) + len(second), timeout=20)

    recorder.stop()
    thread.join(timeout=15)

    logs = sorted((tmp_path / "raw").glob("*.f1raw"))
    assert len(logs) == 2, f"expected two session files, got {[p.name for p in logs]}"
    assert len(recorder.sessions) == 2
    assert {s.session_uid for s in recorder.sessions} == {
        decode_header(first[0]).session_uid,
        12345678901234567890,
    }


def test_a_second_recorder_reports_the_port_conflict(tmp_path: Path) -> None:
    """FR-006: never silently capture nothing because something else holds the port."""
    port = free_port()
    first = Recorder(tmp_path / "raw", tmp_path / "s1.json", port=port, host="127.0.0.1")
    thread = run_recorder(first)
    assert wait_until(lambda: first._sock is not None)

    second = Recorder(tmp_path / "raw2", tmp_path / "s2.json", port=port, host="127.0.0.1")
    result = second.run()

    assert result.exit_code == EXIT_PORT_IN_USE
    assert "another application" in (result.message or "").lower()

    first.stop()
    thread.join(timeout=10)


def test_status_reports_stopped_after_shutdown(tmp_path: Path) -> None:
    port = free_port()
    status_path = tmp_path / "status.json"
    recorder = Recorder(tmp_path / "raw", status_path, port=port, host="127.0.0.1")
    thread = run_recorder(recorder)

    assert wait_until(lambda: status_path.exists(), timeout=10)
    recorder.stop()
    thread.join(timeout=10)

    assert read_status(status_path)["state"] == STATE_STOPPED


def test_no_empty_files_when_nothing_is_received(tmp_path: Path) -> None:
    """User Story 1 scenario 5: idle with the game closed creates no recordings."""
    port = free_port()
    recorder = Recorder(tmp_path / "raw", tmp_path / "status.json", port=port, host="127.0.0.1")
    thread = run_recorder(recorder)
    assert wait_until(lambda: recorder._sock is not None)
    time.sleep(1.0)
    recorder.stop()
    thread.join(timeout=10)

    assert list((tmp_path / "raw").glob("*.f1raw")) == []
    assert recorder.sessions == []
