"""T027 -- unrecognised packets are reported, never coerced.

Constitution principle III and FR-017. A future game patch, or F1 24/25/26, will send
packet formats this build does not know. The failure mode we are ruling out is decoding
them with a neighbouring codec, which yields plausible but meaningless numbers.

Equally important: one unknown packet type must not abort ingest of an otherwise
readable session (spec edge case, "a recording contains information the app cannot yet
interpret").
"""

from __future__ import annotations

import pytest

from f1dc.wire.f1_2023 import CODECS
from f1dc.wire.registry import DuplicateCodecError, Registry, default_registry


@pytest.fixture
def registry() -> Registry:
    r = Registry()
    for codec in CODECS:
        r.register(codec)
    return r


def test_known_packets_dispatch(registry: Registry) -> None:
    for codec in CODECS:
        assert registry.get((2023, codec.packet_id, 1)) is codec
    assert registry.unknown_count == 0


def test_a_future_packet_format_is_not_coerced(registry: Registry) -> None:
    """F1 25 sending format 2025 must not be decoded as 2023."""
    assert registry.get((2025, 2, 1)) is None
    assert registry.unknown_count == 1
    report = " ".join(registry.unknown_report())
    assert "2025" in report
    assert "not supported" in report


def test_an_unknown_packet_id_is_not_coerced(registry: Registry) -> None:
    assert registry.get((2023, 99, 1)) is None
    report = " ".join(registry.unknown_report())
    assert "packet id 99" in report


def test_an_unknown_packet_version_is_not_coerced(registry: Registry) -> None:
    """A patch bumping only the version must not silently reuse the old codec."""
    assert registry.get((2023, 2, 7)) is None
    assert "version 7" in " ".join(registry.unknown_report())


def test_unknown_packets_are_counted_not_merely_dropped(registry: Registry) -> None:
    for _ in range(5):
        registry.get((2025, 0, 1))
    registry.get((2023, 99, 1))
    assert registry.unknown_count == 6
    assert registry.unknown[(2025, 0, 1)] == 5


def test_getting_an_unknown_packet_does_not_raise(registry: Registry) -> None:
    """Ingest must survive it; the session is still worth interpreting."""
    for key in [(2025, 0, 1), (2023, 200, 1), (1999, 2, 1)]:
        assert registry.get(key) is None


def test_registering_two_codecs_for_one_key_is_rejected(registry: Registry) -> None:
    class Impostor(CODECS[0]):  # type: ignore[misc]
        pass

    with pytest.raises(DuplicateCodecError):
        registry.register(Impostor)


def test_reregistering_the_same_codec_is_idempotent(registry: Registry) -> None:
    for codec in CODECS:
        registry.register(codec)
    assert len(registry.known_keys()) == len(CODECS)


def test_the_shipped_registry_knows_only_2023(registry: Registry) -> None:
    assert default_registry.known_formats() == {2023}
    assert len(default_registry.known_keys()) == len(CODECS)
