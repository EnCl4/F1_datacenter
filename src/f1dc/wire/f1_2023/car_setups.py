"""T019 -- PacketCarSetupData, 1107 bytes.

Nothing in feature 001 displays a setup, but it is captured and decoded now because
``fuel_load`` is part of a lap's comparability context (principle VI) and because the
setup notebook is a planned later feature. Tyre pressure fields follow the same
rear-left-first ordering as every other wheel array and are named accordingly.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.registry import register


@dataclass(frozen=True, slots=True)
class CarSetupData:
    front_wing: int
    rear_wing: int
    on_throttle: int
    off_throttle: int
    front_camber: float
    rear_camber: float
    front_toe: float
    rear_toe: float
    front_suspension: int
    rear_suspension: int
    front_anti_roll_bar: int
    rear_anti_roll_bar: int
    front_suspension_height: int
    rear_suspension_height: int
    brake_pressure: int
    brake_bias: int
    rear_left_tyre_pressure: float
    rear_right_tyre_pressure: float
    front_left_tyre_pressure: float
    front_right_tyre_pressure: float
    ballast: int
    fuel_load: float


@register
class CarSetupsCodec(PerCarCodec):
    packet_id = 5
    wire_size = 1107
    name = "CarSetups"

    ITEM = struct.Struct(
        "<"
        "BBBB"  # frontWing, rearWing, onThrottle, offThrottle
        "ffff"  # frontCamber, rearCamber, frontToe, rearToe
        "BBBBBBBB"  # suspension, anti-roll bars, ride heights, brake pressure/bias
        "ffff"  # tyre pressures: RL, RR, FL, FR
        "B"  # ballast
        "f"  # fuelLoad
    )

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> CarSetupData:
        return CarSetupData(*cls.unpack_car(buf, index))
