"""T014-T017, T026, T029 -- lap comparison, the running time gap, and session pace.

Computed per request, not stored, so it belongs neither to ingest nor to the API: this
module is testable without HTTP, and the API is a thin wrapper over it.

The time gap is computed here, once, for the same reason lap validity is computed once in
ingest -- no chart may derive a different answer (constitution principle VI). The same
principle is why two laps from different circuits are refused outright: on a different
circuit, "metre 2 300" is a different place, and a comparison would look valid while
meaning nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import duckdb

from f1dc.config import Paths
from f1dc.store import catalog, layout

LAP_REF = re.compile(r"^(\d+):(\d+)$")

#: Context fields that materially change achievable lap time. Only these feed `differs`;
#: date or session type differing is expected and not a warning (FR-014).
CONTEXT_FIELDS = (
    "assists_summary",
    "tyre",
    "tyre_age_laps",
    "fuel_in_tank_start",
    "weather_name",
    "track_temp_c",
    "ai_difficulty",
)
#: Fuel within this many kilograms counts as the same.
FUEL_TOLERANCE_KG = 1.0


class CompareError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class LapRef:
    session_uid: str
    lap_number: int

    @classmethod
    def parse(cls, text: str) -> LapRef:
        match = LAP_REF.match(text or "")
        if not match:
            raise CompareError(
                "bad_lap_ref", f"'{text}' is not a lap reference; expected <session_uid>:<lap>", 400
            )
        return cls(match.group(1), int(match.group(2)))

    def __str__(self) -> str:
        return f"{self.session_uid}:{self.lap_number}"


# ---------------------------------------------------------------------------- lookups


def _session(paths: Paths, uid: str) -> dict[str, Any]:
    session = catalog.get_session(paths, uid)
    if session is None:
        raise CompareError("session_not_found", f"No session with uid {uid}", 404)
    return session


def _lap(paths: Paths, ref: LapRef) -> dict[str, Any]:
    for lap in catalog.get_laps(paths, ref.session_uid):
        if lap["lap_number"] == ref.lap_number:
            return lap
    raise CompareError("lap_not_found", f"No lap {ref.lap_number} in session {ref.session_uid}", 404)


def _raw_log_exists(paths: Paths, uid: str) -> bool:
    return any(p.name.split(".f1raw")[0].endswith(f"_{uid}") for p in layout.raw_logs(paths))


def _unavailable(paths: Paths, ref: LapRef) -> CompareError:
    """FR-006: say *why* there is no trace, never just show an empty chart."""
    if not _raw_log_exists(paths, ref.session_uid):
        reason = (
            "its original recording no longer exists, so its charts cannot be rebuilt "
            "(lap times are unaffected)"
        )
    else:
        reason = (
            "no telemetry was captured for it -- if this session was recorded before charts "
            "existed, run ingest to rebuild it"
        )
    return CompareError("trace_unavailable", f"Lap {ref.lap_number} has no trace: {reason}", 409)


def sectors_m(lap: dict[str, Any]) -> list[float]:
    return [v for v in (lap.get("sector2_start_m"), lap.get("sector3_start_m")) if v is not None]


def trace(paths: Paths, ref: LapRef) -> dict[str, Any]:
    """One lap's trace, per contracts/http-api.md."""
    session = _session(paths, ref.session_uid)
    lap = _lap(paths, ref)
    channels = catalog.get_trace(paths, ref.session_uid, ref.lap_number)
    if channels is None:
        raise _unavailable(paths, ref)
    return {
        "session_uid": ref.session_uid,
        "lap_number": ref.lap_number,
        "track_id": session["track_id"],
        "track_name": session["track_name"],
        "track_length_m": session["track_length_m"],
        "lap_time_ms": lap["lap_time_ms"],
        "counts": lap["counts"],
        "exclusion_reason": lap["exclusion_reason"],
        "sectors_m": sectors_m(lap),
        "channels": channels,
    }


# ---------------------------------------------------------------------------- comparing


def default_reference(paths: Paths, lap: LapRef) -> LapRef:
    """FR-018: the session's best counting lap."""
    session = _session(paths, lap.session_uid)
    best = session.get("best_lap_number")
    if best is None:
        raise CompareError(
            "reference_incomplete",
            "This session has no counting lap to use as a reference; choose one explicitly",
            409,
        )
    return LapRef(lap.session_uid, int(best))


def context_of(session: dict[str, Any], lap: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_uid": session["session_uid"],
        "lap_number": lap["lap_number"],
        "started_at": session["started_at"],
        "session_type_name": session["session_type_name"],
        "assists_summary": session["assists_summary"],
        "tyre": lap["tyre_visual_compound_name"],
        "tyre_age_laps": lap["tyre_age_laps"],
        "fuel_in_tank_start": (
            round(lap["fuel_in_tank_start"], 1) if lap["fuel_in_tank_start"] is not None else None
        ),
        "weather_name": session["weather_name"],
        "track_temp_c": session["track_temp_c"],
        "ai_difficulty": session["ai_difficulty"],
        "counts": lap["counts"],
        "exclusion_reason": lap["exclusion_reason"],
    }


def differing_fields(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Which lap-time-relevant conditions differ (FR-014)."""
    differs = []
    for name in CONTEXT_FIELDS:
        x, y = a.get(name), b.get(name)
        if name == "fuel_in_tank_start" and x is not None and y is not None:
            if abs(x - y) > FUEL_TOLERANCE_KG:
                differs.append(name)
        elif x != y:
            differs.append(name)
    return differs


def running_gap(lap: dict[str, list], reference: dict[str, list]) -> dict[str, list]:
    """Time behind the reference at every metre (R8). Positive means the lap is behind.

    Both traces sit on the same one-metre grid starting at 0, so index i is metre i in
    both, and the finish anchor of a complete lap sits at index == track length.
    """
    a, b = lap["time_ms"], reference["time_ms"]
    n = min(len(a), len(b))
    gap = [None if a[i] is None or b[i] is None else round(a[i] - b[i], 1) for i in range(n)]
    return {"distance_m": lap["distance_m"][:n], "gap_ms": gap}


def compare(paths: Paths, lap_text: str, reference_text: str | None = None) -> dict[str, Any]:
    lap_ref = LapRef.parse(lap_text)
    ref_ref = LapRef.parse(reference_text) if reference_text else default_reference(paths, lap_ref)

    lap_session, ref_session = _session(paths, lap_ref.session_uid), _session(paths, ref_ref.session_uid)
    lap_row, ref_row = _lap(paths, lap_ref), _lap(paths, ref_ref)

    if lap_session["track_id"] != ref_session["track_id"]:
        raise CompareError(
            "different_circuits",
            f"Cannot compare a lap at {lap_session['track_name']} with one at "
            f"{ref_session['track_name']}: track distance means a different place on each",
            409,
        )
    if not ref_row["lap_time_ms"]:
        raise CompareError(
            "reference_incomplete",
            f"Lap {ref_ref.lap_number} was not completed, so it cannot be the reference",
            409,
        )

    lap_trace, ref_trace = trace(paths, lap_ref), trace(paths, ref_ref)
    lap_ctx, ref_ctx = context_of(lap_session, lap_row), context_of(ref_session, ref_row)

    return {
        "lap": lap_trace,
        "reference": ref_trace,
        "gap": running_gap(lap_trace["channels"], ref_trace["channels"]),
        "context": {
            "lap": lap_ctx,
            "reference": ref_ctx,
            "differs": differing_fields(lap_ctx, ref_ctx),
        },
    }


# ---------------------------------------------------------------------------- pace


def pace(paths: Paths, session_uid: str) -> dict[str, Any]:
    """Session pace chart data (US3). Needs no traces."""
    _session(paths, session_uid)
    laps = [
        {
            "lap_number": lap["lap_number"],
            "lap_time_ms": lap["lap_time_ms"],
            "counts": lap["counts"],
            "exclusion_reason": lap["exclusion_reason"],
            "stint_index": lap["stint_index"],
            "tyre_visual_compound_name": lap["tyre_visual_compound_name"],
        }
        for lap in catalog.get_laps(paths, session_uid)
    ]
    stints = [
        {
            "stint_index": s["stint_index"],
            "start_lap": s["start_lap"],
            "end_lap": s["end_lap"],
            "tyre_visual_compound_name": s["tyre_visual_compound_name"],
        }
        for s in catalog.get_stints(paths, session_uid)
    ]
    return {"laps": laps, "stints": stints}


def laps_at_track(paths: Paths, track_id: int) -> list[dict[str, Any]]:
    """Every lap at a circuit across all sessions, for the lap pickers (FR-007)."""
    if not catalog.has_data(paths):
        return []
    with catalog.connect(paths) as con:
        rows = con.execute(
            f"SELECT s.session_uid, s.started_at, s.session_type_name, l.lap_number, "
            f"l.lap_time_ms, l.counts, l.exclusion_reason "
            f"FROM {catalog.SESSION_VIEW} s JOIN {catalog.LAP_VIEW} l USING (session_uid) "
            f"WHERE s.track_id = ? ORDER BY s.started_at DESC, l.lap_number",
            [track_id],
        ).fetchall()
    traced = _laps_with_traces(paths)
    keys = ("session_uid", "started_at", "session_type_name", "lap_number",
            "lap_time_ms", "counts", "exclusion_reason")
    out = []
    for row in rows:
        item = dict(zip(keys, row, strict=True))
        item["has_trace"] = (item["session_uid"], item["lap_number"]) in traced
        out.append(item)
    return out


def _laps_with_traces(paths: Paths) -> set[tuple[str, int]]:
    glob = layout.session_glob(paths, layout.TRACES_FILE)
    try:
        with duckdb.connect(":memory:") as con:
            rows = con.execute(
                f"SELECT DISTINCT session_uid, lap_number FROM read_parquet('{glob}')"
            ).fetchall()
    except duckdb.Error:
        return set()  # no session has traces yet
    return {(uid, int(n)) for uid, n in rows}
