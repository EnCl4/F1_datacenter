"""T050, T051 -- turning accumulated observations into Session, Stint and Lap rows.

Lap times come from ``SessionHistory``, which is authoritative, and are cross-checked
against the times derived from ``LapData`` transitions. Disagreement sets a flag on the
lap rather than silently preferring one source (T051) -- a mismatch means one of the two
readings is wrong, and hiding that is how a wrong lap table survives.
"""

from __future__ import annotations

from f1dc.ingest import INGEST_VERSION
from f1dc.ingest.sessionizer import LapContext, RawSession
from f1dc.ingest.validity import best_lap, evaluate
from f1dc.models import IngestResult, Lap, Session, Stint
from f1dc.wire.f1_2023 import enums
from f1dc.wire.f1_2023.session_history import SessionHistoryData

#: Tolerance when checking lap time against the sum of its sectors.
SECTOR_SUM_TOLERANCE_MS = 5

#: Tolerance when comparing SessionHistory against LapData-derived times.
SOURCE_AGREEMENT_TOLERANCE_MS = 50


def build_stints(session_uid: str, raw: RawSession) -> list[Stint]:
    """Derive stints from tyre-age evidence, not from SessionHistory's ``endLap``.

    ``SessionHistory.m_tyreStintsEndLaps`` proved unreliable against the reference
    capture: it reported the player's first stint ending on lap 2, while both tyre age
    (3 -> 0 during lap 4) and ``numPitStops`` (0 -> 1 on lap 4) put the stop on lap 4.
    Another car in the same race reported ``endLap = 0``, which is not a lap number at
    all. The compounds in that structure decode correctly, so the offsets are right --
    the field's own values are the problem.

    So boundaries come from the evidence and compounds come from CarStatus. A stint
    begins at the first lap whose starting tyre age is lower than the previous lap's,
    which places the pit lap at the END of the outgoing stint -- matching how a stop is
    normally described ("he pitted on lap 4, so his first stint was laps 1-4").
    """
    numbers = [n for n in sorted(raw.laps) if raw.laps[n]._status_seen]
    if not numbers:
        return []

    boundaries = [numbers[0]]
    previous = raw.laps[numbers[0]]
    for number in numbers[1:]:
        current = raw.laps[number]
        age_dropped = current.tyre_age < previous.tyre_age
        compound_changed = (
            previous.tyre_actual
            and current.tyre_actual
            and current.tyre_actual != previous.tyre_actual
        )
        if age_dropped or compound_changed:
            boundaries.append(number)
        previous = current

    last_lap = max(raw.laps) if raw.laps else numbers[-1]
    stints: list[Stint] = []
    for index, start_lap in enumerate(boundaries):
        is_last = index == len(boundaries) - 1
        end_lap = last_lap if is_last else boundaries[index + 1] - 1
        ctx = raw.laps[start_lap]
        stints.append(
            Stint(
                session_uid=session_uid,
                stint_index=index,
                start_lap=start_lap,
                end_lap=end_lap if (not is_last or raw.ended_naturally) else None,
                tyre_actual_compound=ctx.tyre_actual,
                tyre_actual_compound_name=enums.actual_compound_name(ctx.tyre_actual),
                tyre_visual_compound=ctx.tyre_visual,
                tyre_visual_compound_name=enums.visual_compound_name(ctx.tyre_visual),
                tyre_age_start_laps=ctx.tyre_age,
                num_laps=max(0, end_lap - start_lap + 1),
            )
        )
    return stints


def stint_for_lap(stints: list[Stint], lap_number: int) -> int | None:
    for stint in stints:
        end = stint.end_lap if stint.end_lap is not None else 10**6
        if stint.start_lap <= lap_number <= end:
            return stint.stint_index
    return None


def assists_summary(raw: RawSession) -> str:
    """Human label covering BOTH packets' worth of assists.

    Built from the Session packet and CarStatus together. A summary from the Session
    packet alone would report "no assists" for a driver running full traction control,
    which is precisely the misrepresentation principle VI forbids.
    """
    data = raw.session_data
    parts: list[str] = []

    if raw.traction_control:
        parts.append("TC full" if raw.traction_control >= 2 else "TC medium")
    if raw.anti_lock_brakes:
        parts.append("ABS")

    if data is not None:
        if data.steering_assist:
            parts.append("steering")
        if data.braking_assist:
            parts.append("braking")
        if data.ers_assist:
            parts.append("ERS")
        if data.drs_assist:
            parts.append("DRS")
        if data.dynamic_racing_line:
            parts.append("racing line")
        parts.append("manual gearbox" if data.gearbox_assist <= 1 else "auto gearbox")

    if not parts:
        return "no assists"
    if len(parts) == 1 and parts[0].endswith("gearbox"):
        return f"no assists, {parts[0]}"
    return ", ".join(parts)


def build_laps(raw: RawSession, session_uid: str, stints: list[Stint]) -> list[Lap]:
    history = raw.history
    category = raw.session_data.session_category if raw.session_data else "unknown"

    numbers = sorted(raw.laps)
    if history is not None:
        numbers = sorted(set(numbers) | {i + 1 for i, h in enumerate(history.laps) if h.is_recorded})

    laps: list[Lap] = []
    for number in numbers:
        ctx = raw.laps.get(number) or LapContext(number, 0.0, 0.0)
        entry = history.lap(number) if history is not None else None

        lap_time = entry.lap_time_ms if entry and entry.is_recorded else None
        if lap_time is None:
            lap_time = ctx.lap_time_from_lapdata

        s1 = entry.sector1_ms if entry and entry.is_recorded else ctx.sector1_from_lapdata
        s2 = entry.sector2_ms if entry and entry.is_recorded else ctx.sector2_from_lapdata
        s3 = entry.sector3_ms if entry and entry.is_recorded else None

        # Cross-validation, not silent preference.
        history_mismatch = False
        if entry and entry.is_recorded and ctx.lap_time_from_lapdata:
            delta = abs(entry.lap_time_ms - ctx.lap_time_from_lapdata)
            history_mismatch = delta > SOURCE_AGREEMENT_TOLERANCE_MS

        sector_mismatch = False
        if lap_time and s1 and s2 and s3:
            sector_mismatch = abs((s1 + s2 + s3) - lap_time) > SECTOR_SUM_TOLERANCE_MS

        valid = not ctx.invalid
        s1_valid = s2_valid = s3_valid = valid
        if entry is not None and entry.is_recorded:
            valid = valid and entry.is_valid
            s1_valid, s2_valid, s3_valid = entry.sector_validity

        counts, reason = evaluate(
            session_category=category,
            lap_number=number,
            lap_time_ms=lap_time,
            valid=valid,
            is_in_lap=ctx.saw_in_lap,
            is_out_lap=ctx.saw_out_lap,
            pit_status=ctx.pit_status,
            under_safety_car=ctx.under_safety_car,
        )

        laps.append(
            Lap(
                session_uid=session_uid,
                lap_number=number,
                stint_index=stint_for_lap(stints, number),
                lap_time_ms=lap_time,
                sector1_ms=s1,
                sector2_ms=s2,
                sector3_ms=s3,
                valid=valid,
                sector1_valid=s1_valid,
                sector2_valid=s2_valid,
                sector3_valid=s3_valid,
                counts=counts,
                exclusion_reason=reason,
                is_in_lap=ctx.saw_in_lap,
                is_out_lap=ctx.saw_out_lap,
                pit_status=ctx.pit_status,
                num_pit_stops=ctx.num_pit_stops,
                under_safety_car=ctx.under_safety_car,
                tyre_actual_compound=ctx.tyre_actual,
                tyre_actual_compound_name=enums.actual_compound_name(ctx.tyre_actual),
                tyre_visual_compound=ctx.tyre_visual,
                tyre_visual_compound_name=enums.visual_compound_name(ctx.tyre_visual),
                tyre_age_laps=ctx.tyre_age,
                fuel_in_tank_start=ctx.fuel_in_tank,
                fuel_remaining_laps=ctx.fuel_remaining_laps,
                tyre_wear_rl=ctx.wear_rl,
                tyre_wear_rr=ctx.wear_rr,
                tyre_wear_fl=ctx.wear_fl,
                tyre_wear_fr=ctx.wear_fr,
                car_position=ctx.car_position,
                penalties_s=ctx.penalties_s,
                corner_cutting_warnings=ctx.corner_cutting_warnings,
                sector_sum_mismatch=sector_mismatch,
                history_mismatch=history_mismatch,
            )
        )
    return laps


def build(raw: RawSession, recording_id: str) -> IngestResult:
    """Turn one accumulated session into the rows the store holds."""
    session_uid = str(raw.session_uid)
    data = raw.session_data

    stints = build_stints(session_uid, raw)
    laps = build_laps(raw, session_uid, stints)
    best_ms, best_num = best_lap(laps)

    started = raw.started_at()
    ended = raw.ended_at()

    session = Session(
        session_uid=session_uid,
        recording_id=recording_id,
        started_at=started.isoformat() if started else "",
        ended_at=ended.isoformat() if ended else None,
        duration_s=round(raw.duration_s, 3),
        track_id=data.track_id if data else -1,
        track_name=data.track_name if data else "unknown",
        track_length_m=data.track_length if data else 0,
        session_type=data.session_type if data else 0,
        session_type_name=data.session_type_name if data else "Unknown",
        session_category=data.session_category if data else "unknown",
        total_laps=data.total_laps if data else 0,
        weather=data.weather if data else 0,
        weather_name=data.weather_name if data else "unknown",
        air_temp_c=data.air_temperature if data else 0,
        track_temp_c=data.track_temperature if data else 0,
        ai_difficulty=data.ai_difficulty if data else 0,
        formula=data.formula if data else 0,
        game_mode=data.game_mode if data else 0,
        rule_set=data.rule_set if data else 0,
        network_game=bool(data.network_game) if data else False,
        player_car_index=raw.player_index,
        ended_naturally=raw.ended_naturally,
        end_reason=raw.end_reason,
        started_late=raw.started_late,
        num_laps=len(laps),
        num_counting_laps=sum(1 for lap in laps if lap.counts),
        best_lap_ms=best_ms,
        best_lap_number=best_num,
        loss_pct=round(raw.loss_pct, 4),
        ingest_version=INGEST_VERSION,
        assist_steering=data.steering_assist if data else 0,
        assist_braking=data.braking_assist if data else 0,
        assist_gearbox=data.gearbox_assist if data else 0,
        assist_pit=data.pit_assist if data else 0,
        assist_pit_release=data.pit_release_assist if data else 0,
        assist_ers=data.ers_assist if data else 0,
        assist_drs=data.drs_assist if data else 0,
        assist_racing_line=data.dynamic_racing_line if data else 0,
        assist_racing_line_type=data.dynamic_racing_line_type if data else 0,
        assist_traction_control=raw.traction_control,
        assist_anti_lock_brakes=raw.anti_lock_brakes,
        assists_summary=assists_summary(raw),
    )

    return IngestResult(session=session, stints=stints, laps=laps)
