"""Feature 003 routes: car and race data, and the single write route.

Read routes are thin wrappers over ``f1dc.analysis.car``. ``DELETE`` is the one write the
constitution (1.1.0) allows the UI. It is equally thin: every check -- including the typed
confirmation -- lives in ``f1dc.store.delete``, so the server decides, not the page.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from f1dc.analysis import car as car_data
from f1dc.config import Paths
from f1dc.store.delete import delete_session

router = APIRouter()


def _paths(request: Request) -> Paths:
    return request.app.state.paths


@router.get("/sessions/{session_uid}/car")
async def car(request: Request, session_uid: str) -> dict[str, Any]:
    return {"laps": car_data.lap_car(_paths(request), session_uid)}


@router.get("/sessions/{session_uid}/excursions")
async def excursions(request: Request, session_uid: str) -> dict[str, Any]:
    return {"items": car_data.excursions(_paths(request), session_uid)}


@router.get("/sessions/{session_uid}/field")
async def field(request: Request, session_uid: str) -> dict[str, Any]:
    return car_data.field(_paths(request), session_uid)


@router.get("/sessions/{session_uid}/timeline")
async def timeline(request: Request, session_uid: str) -> dict[str, Any]:
    return car_data.timeline(_paths(request), session_uid)


@router.get("/sessions/{session_uid}/tyre-sets")
async def tyre_sets(request: Request, session_uid: str) -> dict[str, Any]:
    return {"items": car_data.tyre_sets(_paths(request), session_uid)}


@router.delete("/sessions/{session_uid}")
async def delete(request: Request, session_uid: str, confirm: str | None = None) -> dict[str, Any]:
    """Permanently delete a session and its recording. `confirm` must be the circuit name."""
    return delete_session(_paths(request), session_uid, confirm).to_dict()
