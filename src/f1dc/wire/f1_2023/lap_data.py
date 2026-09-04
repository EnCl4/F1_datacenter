"""T016 -- PacketLapData, 1131 bytes.

Two hazards live in this packet, both found against real captured bytes during design:

1. ``last_lap_time_ms`` observed during lap N is the time for lap **N-1**. Attributing it
   to lap N produces a plausible, entirely wrong lap table.
2. Sector times are split across a ``uint16`` millisecond field that saturates at
   65.535 s and a separate minutes field. Reading the millisecond field alone silently
   wraps on any slow sector -- safety car, damage, Monaco.

Both are handled here and regression-tested (T045).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.f1_2023 import enums
from f1dc.wire.registry import register


def combine_sector(milliseconds: int, minutes: int) -> int:
    """Recombine a split sector time into whole milliseconds.

    The game splits sector times because the millisecond field is a ``uint16``. Any
    sector above 65.535 s carries its overflow in the minutes field.
    """
    return minutes * 60_000 + milliseconds


@dataclass(frozen=True, slots=True)
class LapData:
    last_lap_time_ms: int
    """The time for the PREVIOUS lap, not the current one. See module docstring."""

    current_lap_time_ms: int
    sector1_time_ms_part: int
    sector1_time_minutes: int
    sector2_time_ms_part: int
    sector2_time_minutes: int
    delta_to_car_in_front_ms: int
    delta_to_race_leader_ms: int
    lap_distance: float
    total_distance: float
    safety_car_delta: float
    car_position: int
    current_lap_num: int
    pit_status: int
    num_pit_stops: int
    sector: int
    current_lap_invalid: int
    penalties: int
    total_warnings: int
    corner_cutting_warnings: int
    num_unserved_drive_through_pens: int
    num_unserved_stop_go_pens: int
    grid_position: int
    driver_status: int
    result_status: int
    pit_lane_timer_active: int
    pit_lane_time_in_lane_ms: int
    pit_stop_timer_ms: int
    pit_stop_should_serve_pen: int

    @property
    def sector1_ms(self) -> int:
        return combine_sector(self.sector1_time_ms_part, self.sector1_time_minutes)

    @property
    def sector2_ms(self) -> int:
        return combine_sector(self.sector2_time_ms_part, self.sector2_time_minutes)

    @property
    def is_invalid(self) -> bool:
        return bool(self.current_lap_invalid)

    @property
    def is_in_pit_area(self) -> bool:
        return self.pit_status != 0

    @property
    def driver_status_name(self) -> str:
        return enums.driver_status_name(self.driver_status)

    @property
    def result_status_name(self) -> str:
        return enums.result_status_name(self.result_status)

    @property
    def is_out_lap(self) -> bool:
        return self.driver_status == 3

    @property
    def is_in_lap(self) -> bool:
        return self.driver_status == 2


@register
class LapDataCodec(PerCarCodec):
    packet_id = 2
    wire_size = 1131
    name = "LapData"

    ITEM = struct.Struct(
        "<"
        "II"  # lastLapTimeInMS, currentLapTimeInMS
        "HB"  # sector1 milliseconds + minutes
        "HB"  # sector2 milliseconds + minutes
        "HH"  # deltaToCarInFront, deltaToRaceLeader
        "fff"  # lapDistance, totalDistance, safetyCarDelta
        "15B"  # carPosition .. pitLaneTimerActive
        "HH"  # pitLaneTimeInLane, pitStopTimer
        "B"  # pitStopShouldServePen
    )
    TRAILER = struct.Struct("<BB")  # timeTrialPBCarIdx, timeTrialRivalCarIdx

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> LapData:
        return LapData(*cls.unpack_car(buf, index))
