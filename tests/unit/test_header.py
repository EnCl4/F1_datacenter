"""T012 -- packet header decoded from real captured bytes."""

from __future__ import annotations

import pytest

from f1dc.capture.rawlog import Record
from f1dc.wire.header import HEADER_SIZE, MAX_CARS, decode_header, peek_dispatch
from tests.conftest import REFERENCE


def test_header_is_twenty_nine_bytes() -> None:
    assert HEADER_SIZE == 29
    assert MAX_CARS == 22


def test_every_header_in_the_fixture_decodes(records: list[Record]) -> None:
    for rec in records:
        header = decode_header(rec.payload)
        assert header.packet_format == 2023
        assert header.game_year == 23
        assert 0 <= header.packet_id <= 13
        assert 0 <= header.player_car_index < MAX_CARS


def test_player_car_index_matches_the_reference_capture(player_index: int) -> None:
    assert player_index == REFERENCE["player_car_index"]


def test_menu_state_is_identifiable(records: list[Record]) -> None:
    """sessionUID == 0 exists in real captures and must be recognisable (FR-007)."""
    menu = [r for r in records if decode_header(r.payload).is_menu_state]
    assert menu, "fixture should retain the menu-state records"
    assert all(decode_header(r.payload).session_uid == 0 for r in menu)


def test_exactly_one_real_session_plus_menu_state(records: list[Record]) -> None:
    uids = {decode_header(r.payload).session_uid for r in records}
    real = uids - {0}
    assert len(real) == 1, f"expected one real session, found {len(real)}"
    assert 0 in uids


def test_session_time_advances_monotonically_within_a_session(records: list[Record]) -> None:
    """No flashback was performed in the reference capture, so time only moves forward."""
    last = -1.0
    for rec in records:
        header = decode_header(rec.payload)
        if header.is_menu_state:
            continue
        assert header.session_time >= last - 1e-3, "session time went backwards"
        last = max(last, header.session_time)


def test_overall_frame_identifier_never_decreases(records: list[Record]) -> None:
    """Documented not to reset on a flashback, which makes it the reliable monotonic
    clock -- but only for packets that carry a frame counter at all."""
    last = -1
    for rec in records:
        header = decode_header(rec.payload)
        if header.is_menu_state or not header.has_frame_counter:
            continue
        assert header.overall_frame_identifier >= last
        last = max(last, header.overall_frame_identifier)


def test_end_of_session_packets_carry_no_frame_counter(records: list[Record]) -> None:
    """Found against real bytes: the packets sent as a session closes report frame
    identifiers of zero despite arriving ~391 s in, long after frame 42 511.

    The loss metric counts gaps in frame identifiers, so without this the last packets
    of every session would look like a 42 000-frame loss.
    """
    zeroed = [
        decode_header(r.payload)
        for r in records
        if not decode_header(r.payload).is_menu_state
        and not decode_header(r.payload).has_frame_counter
        and decode_header(r.payload).session_time > 10.0
    ]
    assert zeroed, "expected end-of-session packets with zeroed frame counters"

    # Event (session end), SessionHistory (final state), FinalClassification.
    assert {h.packet_id for h in zeroed} <= {3, 8, 11}
    assert all(h.session_time > 300 for h in zeroed), "these arrive at the very end"


def test_dispatch_key_shape(records: list[Record]) -> None:
    header = decode_header(records[0].payload)
    fmt, pid, ver = header.dispatch_key
    assert fmt == 2023
    assert pid == header.packet_id
    assert ver == header.packet_version


def test_peek_dispatch_agrees_with_full_decode(records: list[Record]) -> None:
    for rec in records[:500]:
        assert peek_dispatch(rec.payload) == decode_header(rec.payload).dispatch_key


def test_peek_dispatch_returns_none_for_a_short_buffer() -> None:
    assert peek_dispatch(b"\x00" * 28) is None


def test_game_version_is_formatted() -> None:
    from f1dc.wire.header import PacketHeader

    h = PacketHeader(2023, 23, 1, 6, 1, 2, 12345, 1.0, 10, 10, 19, 255)
    assert h.game_version == "1.06"


def test_decode_raises_on_a_short_buffer() -> None:
    import struct

    with pytest.raises(struct.error):
        decode_header(b"\x00" * 10)
