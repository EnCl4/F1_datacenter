"""T020 -- PacketSessionHistoryData, 1460 bytes.

The game sends this for one car per packet, cycling through all 22. That makes it the
cheap route to the whole field's lap times and tyre stints without recording full-rate
telemetry for anyone but the player -- which is why "player car only" costs far less than
it sounds (research R5, spec Assumptions).

It also carries authoritative per-lap times, which are cross-checked against the times
derived from LapData transitions. Disagreement is a test failure, not a silent preference
for one source (T051).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PacketCodec
from f1dc.wire.f1_2023 import enums
from f1dc.wire.f1_2023.lap_data import combine_sector
from f1dc.wire.header import HEADER_SIZE
from f1dc.wire.registry import register

MAX_LAPS = 100
MAX_STINTS = 8

# lapValidBitFlags
LAP_VALID = 0x01
SECTOR1_VALID = 0x02
SECTOR2_VALID = 0x04
SECTOR3_VALID = 0x08


@dataclass(frozen=True, slots=True)
class LapHistory:
    lap_time_ms: int
    sector1_ms_part: int
    sector1_minutes: int
    sector2_ms_part: int
    sector2_minutes: int
    sector3_ms_part: int
    sector3_minutes: int
    lap_valid_bit_flags: int

    @property
    def sector1_ms(self) -> int:
        return combine_sector(self.sector1_ms_part, self.sector1_minutes)

    @property
    def sector2_ms(self) -> int:
        return combine_sector(self.sector2_ms_part, self.sector2_minutes)

    @property
    def sector3_ms(self) -> int:
        return combine_sector(self.sector3_ms_part, self.sector3_minutes)

    @property
    def is_valid(self) -> bool:
        return bool(self.lap_valid_bit_flags & LAP_VALID)

    @property
    def sector_validity(self) -> tuple[bool, bool, bool]:
        f = self.lap_valid_bit_flags
        return (bool(f & SECTOR1_VALID), bool(f & SECTOR2_VALID), bool(f & SECTOR3_VALID))

    @property
    def is_recorded(self) -> bool:
        """A completed lap. Unused slots in the 100-entry array are all zero."""
        return self.lap_time_ms > 0


@dataclass(frozen=True, slots=True)
class TyreStintHistory:
    end_lap: int
    """255 while this stint is still current."""

    tyre_actual_compound: int
    tyre_visual_compound: int

    @property
    def is_current(self) -> bool:
        return self.end_lap == 255

    @property
    def actual_compound_name(self) -> str:
        return enums.actual_compound_name(self.tyre_actual_compound)

    @property
    def visual_compound_name(self) -> str:
        return enums.visual_compound_name(self.tyre_visual_compound)


@dataclass(frozen=True, slots=True)
class SessionHistoryData:
    car_idx: int
    num_laps: int
    num_tyre_stints: int
    best_lap_time_lap_num: int
    best_sector1_lap_num: int
    best_sector2_lap_num: int
    best_sector3_lap_num: int
    laps: tuple[LapHistory, ...]
    stints: tuple[TyreStintHistory, ...]

    def lap(self, lap_number: int) -> LapHistory | None:
        """One-based lap lookup, matching how the game numbers laps."""
        if 1 <= lap_number <= len(self.laps):
            return self.laps[lap_number - 1]
        return None


@register
class SessionHistoryCodec(PacketCodec):
    packet_id = 11
    wire_size = 1460
    name = "SessionHistory"

    HEAD = struct.Struct("<7B")
    LAP_ITEM = struct.Struct("<IHBHBHBB")
    STINT_ITEM = struct.Struct("<BBB")

    @classmethod
    def computed_size(cls) -> int:
        return (
            HEADER_SIZE
            + cls.HEAD.size
            + cls.LAP_ITEM.size * MAX_LAPS
            + cls.STINT_ITEM.size * MAX_STINTS
        )

    @classmethod
    def decode(cls, buf: bytes | memoryview) -> SessionHistoryData:
        head = cls.HEAD.unpack_from(buf, HEADER_SIZE)
        num_laps = min(head[1], MAX_LAPS)
        num_stints = min(head[2], MAX_STINTS)

        laps_offset = HEADER_SIZE + cls.HEAD.size
        laps = tuple(
            LapHistory(*cls.LAP_ITEM.unpack_from(buf, laps_offset + i * cls.LAP_ITEM.size))
            for i in range(num_laps)
        )

        stints_offset = laps_offset + cls.LAP_ITEM.size * MAX_LAPS
        stints = tuple(
            TyreStintHistory(
                *cls.STINT_ITEM.unpack_from(buf, stints_offset + i * cls.STINT_ITEM.size)
            )
            for i in range(num_stints)
        )

        return SessionHistoryData(*head, laps=laps, stints=stints)
