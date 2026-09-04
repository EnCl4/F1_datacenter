"""T022 -- PacketTyreSetsData, 231 bytes.

Twenty tyre sets for one car (13 dry, 7 wet), cycled one car per packet. Beyond wear and
availability it carries ``lap_delta_time`` -- the game's own estimate of how much time
each set is worth against the fitted one. That is a genuine strategy input for a later
feature, obtained for 231 bytes.

Note the array here is 20 tyre sets, not 22 cars, which is why the base class calls it
``ITEM_COUNT`` rather than a car count.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.f1_2023 import enums
from f1dc.wire.registry import register

TYRE_SET_COUNT = 20


@dataclass(frozen=True, slots=True)
class TyreSet:
    actual_tyre_compound: int
    visual_tyre_compound: int
    wear: int
    available: int
    recommended_session: int
    life_span: int
    usable_life: int
    lap_delta_time_ms: int
    """Lap time delta against the currently fitted set, in milliseconds."""

    fitted: int

    @property
    def is_fitted(self) -> bool:
        return bool(self.fitted)

    @property
    def is_available(self) -> bool:
        return bool(self.available)

    @property
    def actual_compound_name(self) -> str:
        return enums.actual_compound_name(self.actual_tyre_compound)

    @property
    def visual_compound_name(self) -> str:
        return enums.visual_compound_name(self.visual_tyre_compound)


@dataclass(frozen=True, slots=True)
class TyreSetsData:
    car_idx: int
    sets: tuple[TyreSet, ...]
    fitted_idx: int

    @property
    def fitted_set(self) -> TyreSet | None:
        if 0 <= self.fitted_idx < len(self.sets):
            return self.sets[self.fitted_idx]
        return None


@register
class TyreSetsCodec(PerCarCodec):
    packet_id = 12
    wire_size = 231
    name = "TyreSets"

    PREFIX = struct.Struct("<B")  # carIdx
    ITEM = struct.Struct("<7BhB")  # 7 uint8, int16 lap delta, uint8 fitted
    ITEM_COUNT = TYRE_SET_COUNT
    TRAILER = struct.Struct("<B")  # fittedIdx

    @classmethod
    def decode(cls, buf: bytes | memoryview) -> TyreSetsData:
        return TyreSetsData(
            car_idx=cls.unpack_prefix(buf)[0],
            sets=tuple(TyreSet(*cls.unpack_car(buf, i)) for i in range(cls.ITEM_COUNT)),
            fitted_idx=cls.unpack_trailer(buf)[0],
        )
