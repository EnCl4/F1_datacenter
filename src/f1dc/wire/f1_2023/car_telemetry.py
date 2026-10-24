"""T003 -- PacketCarTelemetryData, 1352 bytes.

Source of the per-metre lap traces (speed, throttle, brake, steer, gear, rpm, drs) for
feature 002. Each frame carries the driver's instantaneous inputs and powertrain state,
which are then resampled against lap distance to draw a lap trace.

Wheel arrays in every F1 23 packet are ordered **rear-left, rear-right, front-left,
front-right**. Fields are named per wheel rather than kept as positional tuples so that
ordering cannot be silently mis-mapped.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.registry import register


@dataclass(frozen=True, slots=True)
class CarTelemetryData:
    speed_kph: int
    throttle: float
    """0..1."""
    steer: float
    """-1 full left, +1 full right."""
    brake: float
    """0..1."""
    clutch: int
    gear: int
    """-1 reverse, 0 neutral, 1..8 forward."""
    engine_rpm: int
    drs: int
    rev_lights_percent: int
    rev_lights_bit_value: int

    # brakesTemperature[4] -- rear-left, rear-right, front-left, front-right
    brake_temp_rl: int
    brake_temp_rr: int
    brake_temp_fl: int
    brake_temp_fr: int
    # tyresSurfaceTemperature[4]
    tyre_surface_temp_rl: int
    tyre_surface_temp_rr: int
    tyre_surface_temp_fl: int
    tyre_surface_temp_fr: int
    # tyresInnerTemperature[4]
    tyre_inner_temp_rl: int
    tyre_inner_temp_rr: int
    tyre_inner_temp_fl: int
    tyre_inner_temp_fr: int

    engine_temperature: int

    # tyresPressure[4]
    tyre_pressure_rl: float
    tyre_pressure_rr: float
    tyre_pressure_fl: float
    tyre_pressure_fr: float
    # surfaceType[4]
    surface_type_rl: int
    surface_type_rr: int
    surface_type_fl: int
    surface_type_fr: int


@register
class CarTelemetryCodec(PerCarCodec):
    packet_id = 6
    wire_size = 1352
    name = "CarTelemetry"

    ITEM = struct.Struct(
        "<"
        "H"  # speed (kph)
        "fff"  # throttle, steer, brake
        "B"  # clutch
        "b"  # gear (signed: -1 reverse)
        "H"  # engineRPM
        "B"  # drs
        "B"  # revLightsPercent
        "H"  # revLightsBitValue
        "4H"  # brakesTemperature (RL, RR, FL, FR)
        "4B"  # tyresSurfaceTemperature (RL, RR, FL, FR)
        "4B"  # tyresInnerTemperature (RL, RR, FL, FR)
        "H"  # engineTemperature
        "4f"  # tyresPressure (RL, RR, FL, FR)
        "4B"  # surfaceType (RL, RR, FL, FR)
    )

    TRAILER = struct.Struct(
        "<"
        "B"  # mfdPanelIndex
        "B"  # mfdPanelIndexSecondaryPlayer
        "b"  # suggestedGear
    )

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> CarTelemetryData:
        return CarTelemetryData(*cls.unpack_car(buf, index))
