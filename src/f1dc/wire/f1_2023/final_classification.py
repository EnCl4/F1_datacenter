"""T021 -- PacketFinalClassificationData, 1020 bytes.

Sent once when a race ends. In a single packet it carries every driver's finishing
position, total time, penalties and complete tyre stint history -- the whole field's
strategy for 1020 bytes, with no per-car telemetry recorded.

Its arrival is also the strongest signal that a session reached its natural end (FR-014).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.f1_2023 import enums
from f1dc.wire.registry import register

MAX_STINTS = 8


@dataclass(frozen=True, slots=True)
class FinalClassificationData:
    position: int
    num_laps: int
    grid_position: int
    points: int
    num_pit_stops: int
    result_status: int
    best_lap_time_ms: int
    total_race_time: float
    """Seconds, excluding penalties."""

    penalties_time: int
    num_penalties: int
    num_tyre_stints: int
    tyre_stints_actual: tuple[int, ...]
    tyre_stints_visual: tuple[int, ...]
    tyre_stints_end_laps: tuple[int, ...]

    @property
    def result_status_name(self) -> str:
        return enums.result_status_name(self.result_status)

    @property
    def classified(self) -> bool:
        return self.result_status == 3

    @property
    def stints(self) -> list[dict[str, object]]:
        """The driver's actual stints, trimmed to the count the packet reports."""
        n = min(self.num_tyre_stints, MAX_STINTS)
        return [
            {
                "actual": self.tyre_stints_actual[i],
                "actual_name": enums.actual_compound_name(self.tyre_stints_actual[i]),
                "visual": self.tyre_stints_visual[i],
                "visual_name": enums.visual_compound_name(self.tyre_stints_visual[i]),
                "end_lap": self.tyre_stints_end_laps[i],
            }
            for i in range(n)
        ]


@register
class FinalClassificationCodec(PerCarCodec):
    packet_id = 8
    wire_size = 1020
    name = "FinalClassification"

    PREFIX = struct.Struct("<B")  # numCars
    ITEM = struct.Struct(
        "<"
        "BBBBBB"  # position, numLaps, gridPosition, points, numPitStops, resultStatus
        "I"  # bestLapTimeInMS
        "d"  # totalRaceTime (seconds, no penalties)
        "BBB"  # penaltiesTime, numPenalties, numTyreStints
        "8B"  # tyreStintsActual
        "8B"  # tyreStintsVisual
        "8B"  # tyreStintsEndLaps
    )

    @classmethod
    def num_cars(cls, buf: bytes | memoryview) -> int:
        return cls.unpack_prefix(buf)[0]

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> FinalClassificationData:
        v = cls.unpack_car(buf, index)
        return FinalClassificationData(
            *v[:11],
            tyre_stints_actual=tuple(v[11:19]),
            tyre_stints_visual=tuple(v[19:27]),
            tyre_stints_end_laps=tuple(v[27:35]),
        )

    @classmethod
    def decode_classified(cls, buf: bytes | memoryview) -> list[FinalClassificationData]:
        """Only the cars the packet says are present."""
        return [cls.decode_car(buf, i) for i in range(min(cls.num_cars(buf), cls.ITEM_COUNT))]
