"""T021, T027, T030 -- analysis routes against specs/002-.../contracts/http-api.md."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from f1dc.api.main import create_app
from tests.conftest import REFERENCE_LAPS, REFERENCE_UID

_W = ("fl", "fr", "rl", "rr")
CHANNELS = {
    "distance_m", "time_ms", "speed_kph", "throttle", "brake", "steer", "gear",
    "rpm", "drs", "g_lat", "g_lon", "x", "z",
    # feature 003
    "gap_ahead_ms", "off_track",
    *(f"{kind}_{w}" for kind in ("tyre_surface", "tyre_inner", "brake", "pressure") for w in _W),
}


@pytest.fixture(scope="module")
def client(ingested):
    with TestClient(create_app(ingested)) as test_client:
        yield test_client


def test_trace_shape(client) -> None:
    body = client.get(f"/api/sessions/{REFERENCE_UID}/laps/2/trace").json()
    assert body["lap_number"] == 2
    assert body["track_id"] == 16
    assert body["lap_time_ms"] == REFERENCE_LAPS[2]
    assert set(body["channels"]) == CHANNELS, "channels must be columnar, one array each"
    lengths = {len(v) for v in body["channels"].values()}
    assert lengths == {4295}


def test_trace_carries_sector_boundaries(client) -> None:
    """FR-013. Measured on the full capture: ~1 168 m and ~3 113 m."""
    sectors = client.get(f"/api/sessions/{REFERENCE_UID}/laps/2/trace").json()["sectors_m"]
    assert len(sectors) == 2
    assert 1100 < sectors[0] < 1250
    assert 3050 < sectors[1] < 3200


def test_a_lap_without_a_trace_is_a_409_that_says_why(client) -> None:
    response = client.get(f"/api/sessions/{REFERENCE_UID}/laps/3/trace")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "trace_unavailable"
    assert error["message"]


def test_unknown_lap_is_a_404(client) -> None:
    assert client.get(f"/api/sessions/{REFERENCE_UID}/laps/99/trace").status_code == 404


def test_compare_shape(client) -> None:
    body = client.get(f"/api/compare?lap={REFERENCE_UID}:5&reference={REFERENCE_UID}:2").json()
    assert set(body) == {"lap", "reference", "gap", "context"}
    assert set(body["gap"]) == {"distance_m", "gap_ms"}
    assert set(body["context"]) == {"lap", "reference", "differs"}


def test_compare_gap_ends_at_the_lap_time_difference(client) -> None:
    gap = client.get(f"/api/compare?lap={REFERENCE_UID}:5&reference={REFERENCE_UID}:2").json()["gap"]
    assert gap["gap_ms"][-1] == REFERENCE_LAPS[5] - REFERENCE_LAPS[2]


def test_compare_defaults_the_reference(client) -> None:
    body = client.get(f"/api/compare?lap={REFERENCE_UID}:5").json()
    assert body["reference"]["lap_number"] == 2


def test_compare_rejects_a_malformed_ref(client) -> None:
    response = client.get("/api/compare?lap=nonsense")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_lap_ref"


def test_pace(client) -> None:
    body = client.get(f"/api/sessions/{REFERENCE_UID}/pace").json()
    assert len(body["laps"]) == 5
    assert len(body["stints"]) == 2


def test_laps_at_track(client) -> None:
    items = client.get("/api/laps?track_id=16").json()["items"]
    assert len(items) == 5
    traced = {i["lap_number"] for i in items if i["has_trace"]}
    # Lap 1 has a partial trace too: recording began 853 m in, and the rest is a gap.
    assert {2, 5} <= traced
    assert 3 not in traced


def test_still_no_write_routes(client) -> None:
    """Constitution 1.1.0: the UI is read-only except ONE confirmed action, deleting a
    session. Any other write route added here must fail this test."""
    schema = client.get("/api/openapi.json").json()
    writes = sorted(
        (method, path)
        for path, ops in schema["paths"].items()
        for method in ops
        if method in {"post", "put", "patch", "delete"}
    )
    assert writes == [("delete", "/api/sessions/{session_uid}")], writes
