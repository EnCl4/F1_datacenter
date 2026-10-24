"""T018-T020, T027, T030 -- analysis routes, per specs/002-.../contracts/http-api.md.

Thin by design: every rule lives in ``f1dc.analysis.compare``, which is tested without
HTTP. These handlers only translate its results and refusals into responses.
Still read-only: there are no write routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from f1dc.analysis import compare as analysis
from f1dc.config import Paths

router = APIRouter()


def _paths(request: Request) -> Paths:
    return request.app.state.paths


@router.get("/sessions/{session_uid}/laps/{lap_number}/trace")
async def lap_trace(request: Request, session_uid: str, lap_number: int) -> dict[str, Any]:
    return analysis.trace(_paths(request), analysis.LapRef(session_uid, lap_number))


@router.get("/compare")
async def compare(request: Request, lap: str, reference: str | None = None) -> dict[str, Any]:
    """`reference` omitted -> the lap's session's best counting lap (FR-018)."""
    return analysis.compare(_paths(request), lap, reference)


@router.get("/sessions/{session_uid}/pace")
async def pace(request: Request, session_uid: str) -> dict[str, Any]:
    return analysis.pace(_paths(request), session_uid)


@router.get("/laps")
async def laps(request: Request, track_id: int) -> dict[str, Any]:
    return {"items": analysis.laps_at_track(_paths(request), track_id)}
