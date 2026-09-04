"""T018 -- PacketCarDamageData, 953 bytes.

Wheel arrays in every F1 23 packet are ordered **rear-left, rear-right, front-left,
front-right** -- not front-first. The fields here are named per wheel rather than kept
as positional tuples precisely so that ordering cannot be silently mis-mapped; a mirrored
left/right tyre analysis is the kind of bug nobody notices.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.registry import register


@dataclass(frozen=True, slots=True)
class CarDamageData:
    # tyresWear[4] -- rear-left, rear-right, front-left, front-right
    tyre_wear_rl: float
    tyre_wear_rr: float
    tyre_wear_fl: float
    tyre_wear_fr: float
    # tyresDamage[4]
    tyre_damage_rl: int
    tyre_damage_rr: int
    tyre_damage_fl: int
    tyre_damage_fr: int
    # brakesDamage[4]
    brake_damage_rl: int
    brake_damage_rr: int
    brake_damage_fl: int
    brake_damage_fr: int

    front_left_wing_damage: int
    front_right_wing_damage: int
    rear_wing_damage: int
    floor_damage: int
    diffuser_damage: int
    sidepod_damage: int
    drs_fault: int
    ers_fault: int
    gear_box_damage: int
    engine_damage: int
    engine_mguh_wear: int
    engine_es_wear: int
    engine_ce_wear: int
    engine_ice_wear: int
    engine_mguk_wear: int
    engine_tc_wear: int
    engine_blown: int
    engine_seized: int

    @property
    def tyre_wear(self) -> dict[str, float]:
        return {
            "rl": self.tyre_wear_rl,
            "rr": self.tyre_wear_rr,
            "fl": self.tyre_wear_fl,
            "fr": self.tyre_wear_fr,
        }

    @property
    def max_tyre_wear(self) -> float:
        return max(self.tyre_wear_rl, self.tyre_wear_rr, self.tyre_wear_fl, self.tyre_wear_fr)


@register
class CarDamageCodec(PerCarCodec):
    packet_id = 10
    wire_size = 953
    name = "CarDamage"

    ITEM = struct.Struct(
        "<"
        "4f"  # tyresWear   (RL, RR, FL, FR)
        "4B"  # tyresDamage (RL, RR, FL, FR)
        "4B"  # brakesDamage (RL, RR, FL, FR)
        "18B"  # wing/floor/diffuser/sidepod, faults, gearbox, engine wear, blown, seized
    )

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> CarDamageData:
        return CarDamageData(*cls.unpack_car(buf, index))
