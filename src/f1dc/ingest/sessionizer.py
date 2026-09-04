"""T049 -- one pass over a raw log, producing per-session accumulations.

Two rules from the spec are enforced here:

* ``sessionUID == 0`` is discarded entirely (FR-007). Without it, menu navigation appears
  in the library as a phantom session -- the reference capture contains exactly such a
  block, 14 Event packets belonging to no session.
* A session that reached its natural end is distinguished from one abandoned or
  interrupted (FR-014), using the CHQF/SEND events and the FinalClassification packet.

Accumulation is incremental rather than buffering every packet: an hour of driving at
60 Hz is ~216 000 LapData samples, and only per-lap aggregates are actually needed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from f1dc.capture.rawlog import Record
from f1dc.wire.f1_2023 import UNDECODED_PACKET_IDS
from f1dc.wire.f1_2023.car_damage import CarDamageCodec, CarDamageData
from f1dc.wire.f1_2023.car_setups import CarSetupData, CarSetupsCodec
from f1dc.wire.f1_2023.car_status import CarStatusCodec, CarStatusData
from f1dc.wire.f1_2023.event import EventCodec
from f1dc.wire.f1_2023.final_classification import (
    FinalClassificationCodec,
    FinalClassificationData,
)
from f1dc.wire.f1_2023.lap_data import LapData, LapDataCodec
from f1dc.wire.f1_2023.session import SessionCodec, SessionData
from f1dc.wire.f1_2023.session_history import SessionHistoryCodec, SessionHistoryData
from f1dc.wire.header import decode_header
from f1dc.wire.registry import Registry, default_registry

LOSS_REFERENCE_PACKET = 2
LATE_START_LAP = 1
LATE_START_SECONDS = 30.0


@dataclass
class LapContext:
    """Everything observed about one lap while it was being driven."""

    lap_number: int
    first_seen: float
    last_seen: float

    pit_status: int = 0
    num_pit_stops: int = 0
    invalid: bool = False
    saw_in_lap: bool = False
    saw_out_lap: bool = False
    under_safety_car: bool = False
    car_position: int = 0
    penalties_s: int = 0
    corner_cutting_warnings: int = 0

    lap_time_from_lapdata: int | None = None
    """Captured at the transition to the next lap -- ``m_lastLapTimeInMS`` reported then
    belongs to THIS lap, not the one reporting it."""

    sector1_from_lapdata: int | None = None
    sector2_from_lapdata: int | None = None

    tyre_actual: int = 0
    tyre_visual: int = 0
    tyre_age: int = 0
    """Tyre age at the START of this lap. A drop against the previous lap is a pit stop,
    and is the evidence stints are derived from -- see laps.build_stints."""

    tyre_age_end: int = 0
    fuel_in_tank: float | None = None
    fuel_remaining_laps: float | None = None
    _status_seen: bool = False

    wear_rl: float | None = None
    wear_rr: float | None = None
    wear_fl: float | None = None
    wear_fr: float | None = None


@dataclass
class RawSession:
    """One session's worth of accumulated observations, ready to be turned into rows."""

    session_uid: int
    player_index: int

    session_data: SessionData | None = None
    setup: CarSetupData | None = None
    history: SessionHistoryData | None = None
    classification: FinalClassificationData | None = None

    laps: dict[int, LapContext] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    first_time: float | None = None
    last_time: float | None = None
    captured_at: datetime | None = None
    first_offset: float = 0.0
    last_offset: float = 0.0

    first_frame: int | None = None
    last_frame: int | None = None
    frames_lost: int = 0

    started_late: bool = False
    menu_records: int = 0
    packets: int = 0

    traction_control: int = 0
    anti_lock_brakes: int = 0

    game_version: str = ""
    packet_format: int = 0

    @property
    def frames_expected(self) -> int:
        if self.first_frame is None or self.last_frame is None:
            return 0
        return max(0, self.last_frame - self.first_frame + 1)

    @property
    def loss_pct(self) -> float:
        expected = self.frames_expected
        return 100.0 * self.frames_lost / expected if expected else 0.0

    @property
    def duration_s(self) -> float:
        if self.first_time is None or self.last_time is None:
            return 0.0
        return max(0.0, self.last_time - self.first_time)

    @property
    def ended_naturally(self) -> bool:
        return self.end_reason in ("chequered", "session_end")

    @property
    def end_reason(self) -> str:
        if self.classification is not None or "CHQF" in self.events:
            return "chequered"
        if "SEND" in self.events:
            return "session_end"
        if self.laps:
            return "abandoned"
        return "interrupted"

    def started_at(self) -> datetime | None:
        if self.captured_at is None:
            return None
        return self.captured_at + timedelta(seconds=self.first_offset)

    def ended_at(self) -> datetime | None:
        if self.captured_at is None:
            return None
        return self.captured_at + timedelta(seconds=self.last_offset)


class Sessionizer:
    """Scans records and accumulates one :class:`RawSession` per real session."""

    def __init__(self, captured_at: datetime, registry: Registry | None = None) -> None:
        self.captured_at = captured_at
        self.registry = registry or default_registry
        self.sessions: dict[int, RawSession] = {}
        self.order: list[int] = []
        self.unknown: Counter = Counter()
        self.declared_undecoded: Counter = Counter()
        self.menu_records = 0
        self._safety_car = 0

    # ------------------------------------------------------------------ scanning

    def feed(self, records) -> list[RawSession]:
        for record in records:
            self._feed_one(record)
        return self.result()

    def result(self) -> list[RawSession]:
        return [self.sessions[uid] for uid in self.order]

    def _feed_one(self, record: Record) -> None:
        payload = record.payload
        try:
            header = decode_header(payload)
        except Exception:
            return

        if header.session_uid == 0:
            # Menu state. Never a library entry (FR-007).
            self.menu_records += 1
            return

        codec = self.registry.get(header.dispatch_key)
        if codec is None:
            # Packet types this build deliberately does not decode -- Motion, Participants,
            # CarTelemetry, MotionEx -- are not "unrecognised". They are declared, their
            # bytes are preserved, and a later feature will read them. Only a genuinely
            # unknown format or id is reportable under FR-017.
            if header.packet_id not in UNDECODED_PACKET_IDS or header.packet_format != 2023:
                self.unknown[header.dispatch_key] += 1
            else:
                self.declared_undecoded[header.packet_id] += 1
            return

        session = self.sessions.get(header.session_uid)
        if session is None:
            session = RawSession(
                session_uid=header.session_uid,
                player_index=header.player_car_index,
                captured_at=self.captured_at,
                first_offset=record.timestamp,
                packet_format=header.packet_format,
                game_version=header.game_version,
            )
            self.sessions[header.session_uid] = session
            self.order.append(header.session_uid)
            self._safety_car = 0

        session.packets += 1
        session.last_offset = record.timestamp
        if session.first_time is None:
            session.first_time = header.session_time
        session.last_time = max(session.last_time or 0.0, header.session_time)

        pid = header.packet_id
        if pid == 2:
            self._on_lap_data(session, payload, header)
        elif pid == 1:
            self._on_session(session, payload)
        elif pid == 7:
            self._on_car_status(session, payload)
        elif pid == 10:
            self._on_car_damage(session, payload)
        elif pid == 5:
            self._on_setup(session, payload)
        elif pid == 11:
            self._on_history(session, payload)
        elif pid == 8:
            self._on_classification(session, payload)
        elif pid == 3:
            self._on_event(session, payload)

    # ------------------------------------------------------------------ handlers

    def _on_session(self, session: RawSession, payload: bytes) -> None:
        data = SessionCodec.decode(payload)
        if session.session_data is None:
            # Conditions at the start of the session are what the library reports.
            session.session_data = data
        self._safety_car = data.safety_car_status

    def _on_lap_data(self, session: RawSession, payload: bytes, header) -> None:
        has_frame = header.has_frame_counter
        if has_frame:
            if session.first_frame is None:
                session.first_frame = header.frame_identifier
            elif (
                session.last_frame is not None
                and header.frame_identifier > session.last_frame + 1
            ):
                session.frames_lost += header.frame_identifier - session.last_frame - 1
            session.last_frame = header.frame_identifier

        lap = LapDataCodec.decode_car(payload, session.player_index)
        number = lap.current_lap_num
        if number <= 0:
            return

        if not session.laps:
            session.started_late = (
                number > LATE_START_LAP or header.session_time > LATE_START_SECONDS
            )

        ctx = session.laps.get(number)
        if ctx is None:
            ctx = LapContext(
                lap_number=number,
                first_seen=header.session_time,
                last_seen=header.session_time,
            )
            session.laps[number] = ctx
            self._close_previous_lap(session, number, lap)

        self._accumulate_lap(ctx, lap, header.session_time)

    def _close_previous_lap(self, session: RawSession, number: int, lap: LapData) -> None:
        """Attribute ``m_lastLapTimeInMS`` to the lap it actually belongs to.

        The value reported during lap N is lap N-1's time. Getting this wrong produces a
        plausible, entirely wrong lap table -- it did, on the first analysis pass during
        design.
        """
        previous = session.laps.get(number - 1)
        if previous is None:
            return
        if lap.last_lap_time_ms > 0:
            previous.lap_time_from_lapdata = lap.last_lap_time_ms

    def _accumulate_lap(self, ctx: LapContext, lap: LapData, session_time: float) -> None:
        ctx.last_seen = session_time
        ctx.pit_status = max(ctx.pit_status, lap.pit_status)
        ctx.num_pit_stops = max(ctx.num_pit_stops, lap.num_pit_stops)
        ctx.invalid = ctx.invalid or lap.is_invalid
        ctx.saw_in_lap = ctx.saw_in_lap or lap.is_in_lap
        ctx.saw_out_lap = ctx.saw_out_lap or lap.is_out_lap
        ctx.under_safety_car = ctx.under_safety_car or self._safety_car != 0
        ctx.car_position = lap.car_position or ctx.car_position
        ctx.penalties_s = max(ctx.penalties_s, lap.penalties)
        ctx.corner_cutting_warnings = max(
            ctx.corner_cutting_warnings, lap.corner_cutting_warnings
        )
        if lap.sector1_ms:
            ctx.sector1_from_lapdata = lap.sector1_ms
        if lap.sector2_ms:
            ctx.sector2_from_lapdata = lap.sector2_ms

    def _on_car_status(self, session: RawSession, payload: bytes) -> None:
        status: CarStatusData = CarStatusCodec.decode_car(payload, session.player_index)
        # Traction control and ABS live only here, not in the Session packet.
        session.traction_control = status.traction_control
        session.anti_lock_brakes = status.anti_lock_brakes

        ctx = self._current_lap(session)
        if ctx is None:
            return
        if not ctx._status_seen:
            ctx._status_seen = True
            ctx.tyre_actual = status.actual_tyre_compound
            ctx.tyre_visual = status.visual_tyre_compound
            ctx.tyre_age = status.tyres_age_laps
            ctx.fuel_in_tank = status.fuel_in_tank
            ctx.fuel_remaining_laps = status.fuel_remaining_laps
        ctx.tyre_age_end = status.tyres_age_laps

    def _on_car_damage(self, session: RawSession, payload: bytes) -> None:
        damage: CarDamageData = CarDamageCodec.decode_car(payload, session.player_index)
        ctx = self._current_lap(session)
        if ctx is None:
            return
        ctx.wear_rl = damage.tyre_wear_rl
        ctx.wear_rr = damage.tyre_wear_rr
        ctx.wear_fl = damage.tyre_wear_fl
        ctx.wear_fr = damage.tyre_wear_fr

    def _on_setup(self, session: RawSession, payload: bytes) -> None:
        session.setup = CarSetupsCodec.decode_car(payload, session.player_index)

    def _on_history(self, session: RawSession, payload: bytes) -> None:
        history: SessionHistoryData = SessionHistoryCodec.decode(payload)
        if history.car_idx == session.player_index:
            # Cumulative: the latest packet supersedes every earlier one.
            session.history = history

    def _on_classification(self, session: RawSession, payload: bytes) -> None:
        results = FinalClassificationCodec.decode_classified(payload)
        if session.player_index < len(results):
            session.classification = results[session.player_index]
        elif results:
            session.classification = results[0]

    def _on_event(self, session: RawSession, payload: bytes) -> None:
        code = EventCodec.decode(payload).code
        if not session.events or session.events[-1] != code:
            session.events.append(code)

    @staticmethod
    def _current_lap(session: RawSession) -> LapContext | None:
        if not session.laps:
            return None
        return session.laps[max(session.laps)]


def scan(records, captured_at: datetime, registry: Registry | None = None) -> list[RawSession]:
    """Convenience wrapper: scan an iterable of records into sessions."""
    sessionizer = Sessionizer(captured_at, registry)
    sessions = sessionizer.feed(records)
    for session in sessions:
        session.menu_records = sessionizer.menu_records
    return sessions
