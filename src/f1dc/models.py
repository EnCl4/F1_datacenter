"""Derived entities, per specs/001-session-capture-library/data-model.md.

None of these is the system of record: every one is regenerable from the raw log by
re-running ingest (constitution principle I).

Per-wheel values are named ``_rl``/``_rr``/``_fl``/``_fr`` rather than kept as positional
tuples, because F1 23 orders wheel arrays rear-left first and a silent mirror is the kind
of bug nobody notices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# End reasons, in order of confidence.
END_CHEQUERED = "chequered"
END_SESSION_END = "session_end"
END_ABANDONED = "abandoned"
END_INTERRUPTED = "interrupted"

# Why a lap does not count toward pace statistics.
EXCLUSION_INVALIDATED = "invalidated"
EXCLUSION_IN_LAP = "in_lap"
EXCLUSION_OUT_LAP = "out_lap"
EXCLUSION_PIT = "pit"
EXCLUSION_SAFETY_CAR = "safety_car"
EXCLUSION_FIRST_LAP = "first_lap"
EXCLUSION_INCOMPLETE = "incomplete"


def _clean(value: Any) -> Any:
    return value


@dataclass
class Recording:
    recording_id: str
    path: str
    captured_at: str
    size_bytes: int
    packets_received: int
    frames_lost: int
    loss_pct: float
    queue_high_water: int
    packet_format: int
    game_version: str
    unknown_packets: int
    compressed: bool
    starred: bool
    ingest_version: str
    ingested_at: str | None

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Session:
    session_uid: str
    """Stored as a string: uint64 exceeds what JSON and some engines handle safely."""

    recording_id: str
    started_at: str
    ended_at: str | None
    duration_s: float

    track_id: int
    track_name: str
    track_length_m: int
    session_type: int
    session_type_name: str
    session_category: str
    total_laps: int

    weather: int
    weather_name: str
    air_temp_c: int
    track_temp_c: int
    ai_difficulty: int
    formula: int
    game_mode: int
    rule_set: int
    network_game: bool
    player_car_index: int

    ended_naturally: bool
    end_reason: str
    started_late: bool

    num_laps: int
    num_counting_laps: int
    best_lap_ms: int | None
    best_lap_number: int | None

    loss_pct: float
    ingest_version: str

    # Assist configuration -- from the Session packet...
    assist_steering: int
    assist_braking: int
    assist_gearbox: int
    assist_pit: int
    assist_pit_release: int
    assist_ers: int
    assist_drs: int
    assist_racing_line: int
    assist_racing_line_type: int
    # ...and from CarStatus, which is the only place these two appear.
    assist_traction_control: int
    assist_anti_lock_brakes: int
    assists_summary: str

    @property
    def incomplete(self) -> bool:
        """Drives the visible marking required by FR-023."""
        return not self.ended_naturally or self.loss_pct > 1.0 or self.started_late

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["incomplete"] = self.incomplete
        return row


@dataclass
class Stint:
    session_uid: str
    stint_index: int
    start_lap: int
    end_lap: int | None
    tyre_actual_compound: int
    tyre_actual_compound_name: str
    tyre_visual_compound: int
    tyre_visual_compound_name: str
    tyre_age_start_laps: int
    num_laps: int

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Lap:
    session_uid: str
    lap_number: int
    stint_index: int | None

    lap_time_ms: int | None
    sector1_ms: int | None
    sector2_ms: int | None
    sector3_ms: int | None

    valid: bool
    sector1_valid: bool
    sector2_valid: bool
    sector3_valid: bool

    counts: bool
    exclusion_reason: str | None

    is_in_lap: bool
    is_out_lap: bool
    pit_status: int
    num_pit_stops: int
    under_safety_car: bool

    tyre_actual_compound: int
    tyre_actual_compound_name: str
    tyre_visual_compound: int
    tyre_visual_compound_name: str
    tyre_age_laps: int

    fuel_in_tank_start: float | None
    fuel_remaining_laps: float | None

    tyre_wear_rl: float | None
    tyre_wear_rr: float | None
    tyre_wear_fl: float | None
    tyre_wear_fr: float | None

    car_position: int
    penalties_s: int
    corner_cutting_warnings: int

    sector_sum_mismatch: bool = False
    """True when lap time and the sum of sectors disagree beyond rounding. Flagged rather
    than discarded, so a data-quality problem is visible instead of silently dropped."""

    history_mismatch: bool = False
    """True when the time derived from LapData disagrees with SessionHistory."""

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestResult:
    session: Session
    stints: list[Stint] = field(default_factory=list)
    laps: list[Lap] = field(default_factory=list)
    recording: Recording | None = None
