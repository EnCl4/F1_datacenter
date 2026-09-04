"""T060-T062, T075-T077 -- the read-only routes, per contracts/http-api.md.

The lap route returns **every** lap, each carrying ``counts`` and ``exclusion_reason``,
rather than a pre-filtered list. That is what keeps the validity rule in exactly one
place: no client can re-derive it and disagree (constitution principle VI).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from f1dc.capture.status import read_status
from f1dc.config import Paths
from f1dc.ingest import INGEST_VERSION
from f1dc.store import catalog

router = APIRouter()


def _paths(request: Request) -> Paths:
    return request.app.state.paths


def _not_found(session_uid: str):
    from f1dc.api.main import ApiError

    return ApiError("session_not_found", f"No session with uid {session_uid}", status=404)


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    paths = _paths(request)
    return {
        "status": "ok",
        "ingest_version": INGEST_VERSION,
        "sessions": catalog.session_count(paths),
        "data_dir": str(paths.data_dir),
    }


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    """Recorder state, backing the library's "nothing is recording" banner (FR-029).

    A status file stale by more than ten seconds reports as stopped, so a recorder that
    died without cleaning up never appears to still be running.
    """
    raw = read_status(_paths(request).status_path)
    return {
        "recording": raw.get("recording", False),
        "state": raw.get("state", "stopped"),
        "since": raw.get("since"),
        "session": raw.get("session"),
        "stale": raw.get("stale", False),
        "loss_pct": raw.get("loss_pct", 0.0),
        "free_disk_gb": raw.get("free_disk_gb"),
        "message": raw.get("message"),
    }


@router.get("/sessions")
async def list_sessions(
    request: Request,
    track_id: int | None = None,
    session_category: str | None = None,
    session_type: int | None = None,
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    include_abandoned: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    total, items = catalog.list_sessions(
        _paths(request),
        track_id=track_id,
        session_category=session_category,
        session_type=session_type,
        date_from=date_from,
        date_to=date_to,
        include_abandoned=include_abandoned,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/tracks")
async def tracks(request: Request) -> dict[str, Any]:
    return {"items": catalog.list_tracks(_paths(request))}


@router.get("/sessions/{session_uid}")
async def get_session(request: Request, session_uid: str) -> dict[str, Any]:
    session = catalog.get_session(_paths(request), session_uid)
    if session is None:
        raise _not_found(session_uid)

    # The comparability context, assembled from both packets that carry assists (FR-022).
    session["assists"] = {
        "steering": session.get("assist_steering"),
        "braking": session.get("assist_braking"),
        "gearbox": session.get("assist_gearbox"),
        "pit": session.get("assist_pit"),
        "pit_release": session.get("assist_pit_release"),
        "ers": session.get("assist_ers"),
        "drs": session.get("assist_drs"),
        "racing_line": session.get("assist_racing_line"),
        "racing_line_type": session.get("assist_racing_line_type"),
        "traction_control": session.get("assist_traction_control"),
        "anti_lock_brakes": session.get("assist_anti_lock_brakes"),
    }
    session["conditions"] = {
        "weather_name": session.get("weather_name"),
        "air_temp_c": session.get("air_temp_c"),
        "track_temp_c": session.get("track_temp_c"),
    }
    return session


@router.get("/sessions/{session_uid}/laps")
async def get_laps(request: Request, session_uid: str) -> dict[str, Any]:
    paths = _paths(request)
    if catalog.get_session(paths, session_uid) is None:
        raise _not_found(session_uid)
    return {"items": catalog.get_laps(paths, session_uid)}


@router.get("/sessions/{session_uid}/stints")
async def get_stints(request: Request, session_uid: str) -> dict[str, Any]:
    paths = _paths(request)
    if catalog.get_session(paths, session_uid) is None:
        raise _not_found(session_uid)
    return {"items": catalog.get_stints(paths, session_uid)}
