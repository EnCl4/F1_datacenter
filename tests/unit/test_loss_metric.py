"""Packet-loss measurement (FR-003), revised after it misreported real sessions.

The first version counted gaps in ``frameIdentifier`` as loss. At the 60 Hz send rate the
game does not send every frame number, so sessions with zero real loss reported 5-18%,
and 15 of the owner's 35 sessions were wrongly marked incomplete. Measured directly, the
six worst of them had exactly one incomplete frame in ~1.27 million.

The rule now: loss is datagrams missing from frames that were sent (every sent frame
carries LapData, Motion and CarTelemetry), plus bursts of whole frames -- frame gaps far
larger than the game's normal skips -- scaled by how often the game sends at all.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from f1dc.capture.loss import BURST_GAP_FRAMES, LossMeter
from f1dc.capture.recorder import Recorder, SessionRecord
from f1dc.wire.header import HEADER, HEADER_SIZE

SESSION_UID = 999
SIZES = {0: 1349, 1: 644, 2: 1131, 3: 45, 6: 1352, 7: 1239}
TRACK_LAP_OFFSET = HEADER_SIZE + 19 * 50 + 31  # player index 19, currentLapNum


def feed_frames(meter: LossMeter, frames, *, packets=(2, 0, 6)) -> LossMeter:
    for frame in frames:
        for pid in packets:
            meter.observe(pid, frame)
    # The final frame stays open (a frame is only judged once the next one starts), which
    # is also what keeps a live recorder from flagging the frame still arriving.
    return meter


# ---------------------------------------------------------------- the meter itself


def test_complete_frames_with_no_gaps_have_no_loss() -> None:
    assert feed_frames(LossMeter(), range(1000)).loss_pct == 0.0


def test_send_rate_skips_are_not_loss() -> None:
    """THE regression. A ~67 fps game at the 60 Hz send rate skips about one frame number
    in ten -- Catalunya showed 20 789 such one-frame skips and reported 10.95% loss."""
    frames = [f for f in range(10_000) if f % 10 != 0]
    meter = feed_frames(LossMeter(), frames)
    meter.observe(2, 9_999 + 1)  # no burst at the end either
    assert meter.missing_datagrams == 0
    assert meter.burst_frames == 0


@pytest.mark.parametrize("stride", [2, 3, 4])
def test_regular_skips_up_to_the_burst_threshold_are_not_loss(stride: int) -> None:
    """At a 60 Hz send rate even a 240 fps game skips at most 3 frame numbers."""
    meter = LossMeter()
    for frame in range(0, 5_000, stride):
        for pid in (2, 0, 6):
            meter.observe(pid, frame)
    assert meter.burst_frames == 0
    assert stride - 1 <= BURST_GAP_FRAMES


def test_a_missing_datagram_is_loss() -> None:
    meter = LossMeter()
    for frame in range(300):
        for pid in (2, 0, 6):
            if not (frame == 100 and pid == 0):
                meter.observe(pid, frame)
    meter.observe(2, 300)
    assert meter.missing_datagrams == 1
    assert meter.frames_lost == pytest.approx(1 / 3)


def test_a_burst_of_whole_frames_is_loss() -> None:
    """The 79-frame hole in the reference capture: frame numbers jump by 79."""
    frames = [f for f in range(2_000) if not (1_000 < f < 1_079)]
    meter = feed_frames(LossMeter(), frames)
    assert meter.burst_frames == 78
    assert meter.frames_lost == pytest.approx(78, abs=1)
    assert 3.0 < meter.loss_pct < 4.5


def test_a_burst_is_scaled_by_how_often_the_game_sends() -> None:
    """When the game only sends every other frame, a 100-number hole held ~50 sent frames."""
    frames = [f for f in range(0, 2_000, 2) if not (1_000 <= f <= 1_100)]
    meter = feed_frames(LossMeter(), frames)
    assert meter.send_ratio == pytest.approx(0.5, abs=0.05)
    assert meter.frames_lost == pytest.approx(50, abs=5)


def test_untracked_packets_are_ignored() -> None:
    meter = feed_frames(LossMeter(), range(100), packets=(2, 0, 6, 7, 10))
    assert meter.missing_datagrams == 0


def test_a_backwards_frame_is_not_a_burst() -> None:
    """A flashback or restart rewinds frame numbers; that is not loss."""
    meter = feed_frames(LossMeter(), [*range(500), *range(200, 400)])
    assert meter.burst_frames == 0


# ---------------------------------------------------------------- through the recorder


def make_packet(
    packet_id: int,
    frame: int,
    *,
    session_uid: int = SESSION_UID,
    session_time: float = 2.0,
    overall: int | None = None,
    lap: int = 1,
) -> bytes:
    """``overall`` defaults to ``frame + 1000``, as in real captures: it does not reset per
    session, so only end-of-session packets have both counters at zero."""
    header = HEADER.pack(
        2023, 23, 1, 21, 1, packet_id, session_uid, session_time,
        frame, (frame + 1000) if overall is None else overall, 19, 255,
    )
    packet = bytearray(header + bytes(SIZES.get(packet_id, 100) - HEADER_SIZE))
    if packet_id == 2:
        packet[TRACK_LAP_OFFSET] = lap
    return bytes(packet)


def make_recorder(tmp_path: Path) -> Recorder:
    return Recorder(tmp_path / "raw", tmp_path / "status.json", port=0)


def send_frames(recorder: Recorder, frames, **kwargs) -> SessionRecord:
    i = 0
    for frame in frames:
        for pid in (2, 0, 6):
            recorder._handle(make_packet(pid, frame, **kwargs), float(i))
            i += 1
    assert recorder.current is not None
    return recorder.current


def test_recorder_reports_no_loss_at_the_60hz_cadence(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    session = send_frames(recorder, [f for f in range(3_000) if f % 9 != 0])
    assert session.loss_pct == 0.0
    recorder._close_session()


def test_end_of_session_packets_with_zeroed_counters_are_not_frames(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    session = send_frames(recorder, range(1_000))
    for pid in (3, 11, 8):
        recorder._handle(make_packet(pid, 0, overall=0, session_time=391.0), 0.0)
    assert session.loss_pct == 0.0
    recorder._close_session()


def test_menu_traffic_does_not_open_a_session(tmp_path: Path) -> None:
    """FR-007: sessionUID == 0 must never create a recording of its own."""
    recorder = make_recorder(tmp_path)
    for i in range(20):
        recorder._handle(make_packet(3, 0, session_uid=0), float(i))
    assert recorder.current is None
    assert recorder.sessions == []


def test_menu_traffic_is_kept_once_a_session_is_open(tmp_path: Path) -> None:
    """Written to the open file and discarded later by ingest -- capture never filters."""
    recorder = make_recorder(tmp_path)
    recorder._handle(make_packet(2, 0), 0.0)
    for i in range(5):
        recorder._handle(make_packet(3, 0, session_uid=0), float(i))
    assert recorder.current is not None
    assert recorder.current.menu_records == 5
    recorder._close_session()


def test_late_start_is_detected(tmp_path: Path) -> None:
    """FR-027: the driver must be told the earlier laps were not captured."""
    recorder = make_recorder(tmp_path)
    session = send_frames(recorder, range(10), lap=4, session_time=180.0)
    assert session.started_late is True
    recorder._close_session()


def test_a_normal_start_is_not_flagged_late(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    session = send_frames(recorder, range(10), lap=1, session_time=2.0)
    assert session.started_late is False
    recorder._close_session()


def test_session_metadata_offsets(tmp_path: Path) -> None:
    """The two bytes the launcher needs to name the circuit."""
    recorder = make_recorder(tmp_path)
    recorder._handle(make_packet(2, 0), 0.0)
    session_packet = bytearray(make_packet(1, 1))
    session_packet[HEADER_SIZE + 6] = 10  # sessionType = Race
    struct.pack_into("<b", session_packet, HEADER_SIZE + 7, 16)  # trackId = Interlagos
    recorder._handle(bytes(session_packet), 1.0)
    assert recorder.current is not None
    assert recorder.current.session_type == 10
    assert recorder.current.track_id == 16
    recorder._close_session()
