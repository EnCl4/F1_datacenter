"""Motion and CarTelemetry decoded from the reference capture.

CarTelemetry supplies the per-frame driver inputs for feature 002's lap traces; Motion
supplies the g-forces and world positions. The cross-check ties the two together: their
independently-derived speeds must agree, which is what verified the Motion layout.
"""

from __future__ import annotations

import pytest

from f1dc.wire.f1_2023 import OBSERVED_WIRE_SIZES
from f1dc.wire.f1_2023.car_telemetry import CarTelemetryCodec
from f1dc.wire.f1_2023.motion import MotionCodec
from f1dc.wire.header import decode_header
from tests.conftest import first_of

#: Motion and CarTelemetry agree within this many km/h when both are correct.
SPEED_TOLERANCE_KPH = 2.0
#: Fraction of matched frames that must agree.
MIN_AGREEMENT = 0.90
#: Fewer matched frames than this and the cross-check says nothing.
MIN_MATCHED_FRAMES = 5


# --------------------------------------------------------------------------------------
# Wire sizes
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("codec", [MotionCodec, CarTelemetryCodec], ids=lambda c: c.name)
def test_wire_size_matches_observed(codec, by_packet_id) -> None:
    assert codec.wire_size == OBSERVED_WIRE_SIZES[codec.packet_id]
    assert len(first_of(by_packet_id, codec.packet_id)) == codec.wire_size


# --------------------------------------------------------------------------------------
# CarTelemetry
# --------------------------------------------------------------------------------------


def test_car_telemetry_decodes_every_frame_for_the_player(by_packet_id, player_index) -> None:
    records = by_packet_id.get(6, [])
    if not records:
        pytest.skip("fixture contains no packet id 6")
    for rec in records:
        t = CarTelemetryCodec.decode_car(rec.payload, player_index)
        assert 0 <= t.speed_kph <= 400, f"speed {t.speed_kph} out of range"
        assert 0.0 <= t.throttle <= 1.0
        assert 0.0 <= t.brake <= 1.0
        assert -1.0 <= t.steer <= 1.0
        assert -1 <= t.gear <= 8, f"gear {t.gear} out of range"
        assert 0 <= t.engine_rpm <= 16_000, f"rpm {t.engine_rpm} out of range"


# --------------------------------------------------------------------------------------
# Motion
# --------------------------------------------------------------------------------------


def test_motion_decodes_every_frame_for_the_player(by_packet_id, player_index) -> None:
    records = by_packet_id.get(0, [])
    if not records:
        pytest.skip("fixture contains no packet id 0")
    for rec in records:
        m = MotionCodec.decode_car(rec.payload, player_index)
        assert -8.0 <= m.g_force_lateral <= 8.0
        assert -8.0 <= m.g_force_longitudinal <= 8.0
        assert -8.0 <= m.g_force_vertical <= 8.0


# --------------------------------------------------------------------------------------
# Cross-check: Motion speed against CarTelemetry speed, frame by frame
# --------------------------------------------------------------------------------------


def test_motion_speed_agrees_with_car_telemetry(by_packet_id, player_index) -> None:
    telemetry_by_frame = {}
    for rec in by_packet_id.get(6, []):
        frame = decode_header(rec.payload).frame_identifier
        telemetry_by_frame[frame] = CarTelemetryCodec.decode_car(rec.payload, player_index)

    pairs = []
    for rec in by_packet_id.get(0, []):
        frame = decode_header(rec.payload).frame_identifier
        telemetry = telemetry_by_frame.get(frame)
        if telemetry is None:
            continue
        motion = MotionCodec.decode_car(rec.payload, player_index)
        pairs.append((motion.speed_kph, telemetry.speed_kph))

    if len(pairs) < MIN_MATCHED_FRAMES:
        pytest.skip(f"only {len(pairs)} frames matched between Motion and CarTelemetry")

    agreeing = sum(1 for motion_kph, telemetry_kph in pairs
                   if abs(motion_kph - telemetry_kph) <= SPEED_TOLERANCE_KPH)
    ratio = agreeing / len(pairs)
    assert ratio >= MIN_AGREEMENT, (
        f"Motion and CarTelemetry speeds agree on {ratio:.1%} of {len(pairs)} frames; "
        f"need {MIN_AGREEMENT:.0%}"
    )
