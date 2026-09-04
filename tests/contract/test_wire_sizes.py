"""T025 -- wire sizes asserted against reality, not against the source file.

Constitution principle IV. ``OBSERVED_WIRE_SIZES`` is what the game actually sent in the
reference capture; the codecs' declared sizes must match it, and every packet in the
fixture must arrive at exactly that length.

A binary offset error produces plausible but wrong numbers rather than a crash, so this
is the check that stands between us and silently corrupt analysis.
"""

from __future__ import annotations

import pytest

from f1dc.capture.rawlog import Record
from f1dc.wire.f1_2023 import CODECS, OBSERVED_WIRE_SIZES, UNDECODED_PACKET_IDS
from f1dc.wire.header import decode_header


@pytest.mark.parametrize("codec", CODECS, ids=lambda c: c.name)
def test_declared_size_matches_observed(codec) -> None:
    observed = OBSERVED_WIRE_SIZES[codec.packet_id]
    assert codec.wire_size == observed, (
        f"{codec.name} declares {codec.wire_size} bytes but the game sent {observed}"
    )


@pytest.mark.parametrize("codec", CODECS, ids=lambda c: c.name)
def test_fields_sum_to_declared_size(codec) -> None:
    """The same assertion the codec runs at import, made visible as a test."""
    assert codec.computed_size() == codec.wire_size


def test_every_packet_in_fixture_has_its_expected_size(records: list[Record]) -> None:
    """Not one sampled packet -- every packet in the fixture."""
    wrong: list[str] = []
    for rec in records:
        header = decode_header(rec.payload)
        expected = OBSERVED_WIRE_SIZES.get(header.packet_id)
        if expected is None:
            wrong.append(f"unexpected packet id {header.packet_id}")
        elif len(rec.payload) != expected:
            wrong.append(
                f"packet id {header.packet_id}: got {len(rec.payload)}, expected {expected}"
            )
    assert not wrong, f"{len(wrong)} size mismatches, first few: {wrong[:5]}"


def test_all_thirteen_packet_types_present(by_packet_id: dict[int, list[Record]]) -> None:
    """The fixture must exercise every packet type the game emits."""
    present = set(by_packet_id)
    expected = set(OBSERVED_WIRE_SIZES)
    assert present == expected, f"missing {expected - present}, unexpected {present - expected}"


def test_undecoded_ids_are_declared_not_forgotten() -> None:
    """Packet types we choose not to decode are documented, not silently ignored.

    Every packet id the game was observed to send must be either decoded by a codec or
    listed with a reason. LobbyInfo (9) is declared but never observed, because the
    reference capture was single-player.
    """
    decoded = {c.packet_id for c in CODECS}
    undecoded = set(UNDECODED_PACKET_IDS)
    observed = set(OBSERVED_WIRE_SIZES)

    assert decoded.isdisjoint(undecoded), "a packet id is both decoded and declared undecoded"
    unaccounted = observed - decoded - undecoded
    assert not unaccounted, f"observed packet ids with neither codec nor reason: {unaccounted}"


def test_packet_format_is_2023(records: list[Record]) -> None:
    formats = {decode_header(r.payload).packet_format for r in records}
    assert formats == {2023}, f"expected only format 2023, saw {formats}"
