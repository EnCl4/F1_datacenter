"""T030 -- packet loss accounting.

FR-003 requires each session to report how much telemetry it lost. The measurement is
gaps in the reference packet's frame identifiers -- with the exclusion that end-of-session
packets carry zeroed counters, found against real bytes and worth a phantom 42 000-frame
loss per session if forgotten.
"""

from __future__ import annotations

import struct
from pathlib import Path

from f1dc.capture.recorder import LOSS_REFERENCE_PACKET, Recorder, SessionRecord
from f1dc.wire.header import HEADER, HEADER_SIZE

SESSION_UID = 999
TRACK_LAP_OFFSET = HEADER_SIZE + 19 * 50 + 31  # player index 19, currentLapNum


def make_packet(
    packet_id: int,
    frame: int,
    *,
    session_uid: int = SESSION_UID,
    session_time: float = 2.0,
    overall: int | None = None,
    lap: int = 1,
    size: int = 1131,
) -> bytes:
    """Build a synthetic packet.

    ``overall`` defaults to ``frame + 1000`` rather than to ``frame``, matching real
    captures: overallFrameIdentifier is a running counter that does not reset per
    session, so a session's frame 0 still carries a large overall value. Only the
    end-of-session packets have both at zero -- which is exactly what makes them
    distinguishable.
    """
    header = HEADER.pack(
        2023, 23, 1, 21, 1, packet_id, session_uid, session_time,
        frame, (frame + 1000) if overall is None else overall, 19, 255,
    )
    body = bytearray(size - HEADER_SIZE)
    packet = bytearray(header + bytes(body))
    if packet_id == LOSS_REFERENCE_PACKET and len(packet) > TRACK_LAP_OFFSET:
        packet[TRACK_LAP_OFFSET] = lap
    return bytes(packet)


def make_recorder(tmp_path: Path) -> Recorder:
    return Recorder(tmp_path / "raw", tmp_path / "status.json", port=0)


def feed(recorder: Recorder, packets: list[bytes]) -> SessionRecord:
    for i, payload in enumerate(packets):
        recorder._handle(payload, float(i))
    assert recorder.current is not None
    return recorder.current


def test_no_gaps_means_no_loss(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    session = feed(recorder, [make_packet(2, f) for f in range(100)])
    assert session.frames_lost == 0
    assert session.loss_pct == 0.0
    assert session.frames_expected == 100
    recorder._close_session()


def test_a_single_gap_is_counted(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    frames = list(range(50)) + list(range(60, 100))  # ten frames missing
    session = feed(recorder, [make_packet(2, f) for f in frames])
    assert session.frames_lost == 10
    assert session.frames_expected == 100
    assert session.loss_pct == 10.0
    recorder._close_session()


def test_the_measured_baseline_reproduces(tmp_path: Path) -> None:
    """The reference capture lost 82 frames of 39 991: 0.205%."""
    recorder = make_recorder(tmp_path)
    frames = [f for f in range(40_073) if not (10_000 <= f < 10_079) and f % 10_000 != 3]
    session = feed(recorder, [make_packet(2, f) for f in frames])
    assert session.frames_lost == 79 + 4
    assert 0.1 < session.loss_pct < 0.3
    recorder._close_session()


def test_zeroed_frame_counters_are_excluded(tmp_path: Path) -> None:
    """The finding that matters: end-of-session packets report frame 0.

    Without the exclusion, the final packets of every session would look like the entire
    session had been lost, making SC-002 unmeasurable and flagging every session
    incomplete under FR-023.
    """
    recorder = make_recorder(tmp_path)
    packets = [make_packet(2, f) for f in range(1000)]
    packets.append(make_packet(2, 0, overall=0, session_time=391.0))  # the end-of-session packet
    session = feed(recorder, packets)

    assert session.frames_lost == 0, "zeroed counters were treated as a real frame"
    assert session.last_frame == 999, "the zeroed packet must not move the frame cursor"
    recorder._close_session()


def test_only_the_reference_packet_drives_the_metric(tmp_path: Path) -> None:
    """Other packet types arrive at their own rates; counting them would invent losses."""
    recorder = make_recorder(tmp_path)
    packets: list[bytes] = []
    for f in range(100):
        packets.append(make_packet(2, f))
        if f % 30 == 0:
            packets.append(make_packet(1, f, size=644))  # Session, 2 Hz
    session = feed(recorder, packets)
    assert session.frames_lost == 0
    recorder._close_session()


def test_menu_traffic_does_not_open_a_session(tmp_path: Path) -> None:
    """FR-007: sessionUID == 0 must never create a recording of its own."""
    recorder = make_recorder(tmp_path)
    for i in range(20):
        recorder._handle(make_packet(3, 0, session_uid=0, size=45), float(i))
    assert recorder.current is None
    assert recorder.sessions == []


def test_menu_traffic_is_kept_once_a_session_is_open(tmp_path: Path) -> None:
    """It is written to the open file and discarded later by ingest, per the raw-log
    contract -- capture never filters."""
    recorder = make_recorder(tmp_path)
    recorder._handle(make_packet(2, 0), 0.0)
    for i in range(5):
        recorder._handle(make_packet(3, 0, session_uid=0, size=45), float(i))
    assert recorder.current is not None
    assert recorder.current.menu_records == 5
    recorder._close_session()


def test_late_start_is_detected(tmp_path: Path) -> None:
    """FR-027: the driver must be told the earlier laps were not captured."""
    recorder = make_recorder(tmp_path)
    session = feed(recorder, [make_packet(2, f, lap=4, session_time=180.0) for f in range(10)])
    assert session.started_late is True
    recorder._close_session()


def test_a_normal_start_is_not_flagged_late(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    session = feed(recorder, [make_packet(2, f, lap=1, session_time=2.0) for f in range(10)])
    assert session.started_late is False
    recorder._close_session()


def test_session_metadata_offsets(tmp_path: Path) -> None:
    """The two bytes the launcher needs to name the circuit."""
    recorder = make_recorder(tmp_path)
    recorder._handle(make_packet(2, 0), 0.0)

    session_packet = bytearray(make_packet(1, 1, size=644))
    session_packet[HEADER_SIZE + 6] = 10  # sessionType = Race
    struct.pack_into("<b", session_packet, HEADER_SIZE + 7, 16)  # trackId = Interlagos
    recorder._handle(bytes(session_packet), 1.0)

    assert recorder.current is not None
    assert recorder.current.session_type == 10
    assert recorder.current.track_id == 16
    recorder._close_session()
