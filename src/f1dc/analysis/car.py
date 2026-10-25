"""Readers for feature 003's per-session tables.

A session ingested before 1.2.0 has none of these files. That is reported as
``data_unavailable``, with the remedy, never as empty lists that would read as "this
session had no tyre data" (contracts/http-api.md).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import duckdb

from f1dc.analysis.compare import CompareError
from f1dc.config import Paths
from f1dc.store import catalog, layout


def _require_session(paths: Paths, uid: str) -> dict[str, Any]:
    session = catalog.get_session(paths, uid)
    if session is None:
        raise CompareError("session_not_found", f"No session with uid {uid}", 404)
    return session


def _read(paths: Paths, uid: str, filename: str, order: str | None = None) -> list[dict[str, Any]]:
    _require_session(paths, uid)
    path: Path = layout.session_dir(paths, uid) / filename
    if not path.exists():
        raise CompareError(
            "data_unavailable",
            "This session was processed before car and race data existed. "
            "Run ingest (or reopen the Library) to add it -- no re-driving needed.",
            409,
        )
    sql = f"SELECT * FROM read_parquet('{path.as_posix()}')"
    if order:
        sql += f" ORDER BY {order}"
    with duckdb.connect(":memory:") as con:
        cursor = con.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
    for row in rows:
        row.pop("session_uid", None)
        for key, value in row.items():
            if isinstance(value, float) and math.isnan(value):
                row[key] = None
    return rows


def lap_car(paths: Paths, uid: str) -> list[dict[str, Any]]:
    return _read(paths, uid, layout.LAP_CAR_FILE, "lap_number")


def excursions(paths: Paths, uid: str) -> list[dict[str, Any]]:
    return _read(paths, uid, layout.EXCURSIONS_FILE, "lap_number, start_m")


def tyre_sets(paths: Paths, uid: str) -> list[dict[str, Any]]:
    return _read(paths, uid, layout.TYRE_SETS_FILE, "set_index")


def timeline(paths: Paths, uid: str) -> dict[str, Any]:
    return {
        "conditions": _read(paths, uid, layout.TIMELINE_FILE, "session_time_s"),
        "events": _read(paths, uid, layout.EVENTS_FILE, "session_time_s"),
    }


def field(paths: Paths, uid: str) -> dict[str, Any]:
    cars = _read(paths, uid, layout.FIELD_FILE)
    timed = sorted((c for c in cars if c["best_lap_ms"]), key=lambda c: c["best_lap_ms"])
    untimed = [c for c in cars if not c["best_lap_ms"]]
    ranked = timed + untimed
    player_rank = next((i + 1 for i, c in enumerate(timed) if c["is_player"]), None)
    return {
        "cars": ranked,
        "player_rank": player_rank,
        "ranked_count": len(timed),
        "laps": _read(paths, uid, layout.FIELD_LAPS_FILE, "car_idx, lap_number"),
    }
