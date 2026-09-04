"""T048, T071 -- the HTTP API against contracts/http-api.md.

Two properties beyond the response shapes:

* the API is **read-only** -- no route mutates anything, which is what keeps the derived
  store single-writer;
* the lap route returns every lap with its ``exclusion_reason``, so the validity rule
  lives in exactly one place (constitution principle VI).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from f1dc.api.main import create_app
from f1dc.capture.status import STATE_RECORDING, RecorderStatus, SessionStatus, write_status
from f1dc.ingest import INGEST_VERSION
from tests.conftest import REFERENCE_LAPS, REFERENCE_UID


@pytest.fixture(scope="module")
def client(ingested):
    with TestClient(create_app(ingested)) as test_client:
        yield test_client


# ---------------------------------------------------------------- health and status


def test_health(client) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["ingest_version"] == INGEST_VERSION
    assert body["sessions"] == 1


def test_status_reports_stopped_when_nothing_is_recording(client) -> None:
    """FR-029: the library must never imply a session is being captured when it is not."""
    body = client.get("/api/status").json()
    assert body["recording"] is False
    assert body["state"] == "stopped"
    assert body["session"] is None


def test_status_reflects_a_live_recorder(client, ingested) -> None:
    write_status(
        ingested.status_path,
        RecorderStatus(
            state=STATE_RECORDING,
            session=SessionStatus("1", track_id=16, session_type=10, current_lap=2,
                                  started_late=False),
        ),
    )
    body = client.get("/api/status").json()
    assert body["recording"] is True
    assert body["session"]["track_id"] == 16
    ingested.status_path.unlink(missing_ok=True)


# ---------------------------------------------------------------- session list


def test_list_sessions(client) -> None:
    body = client.get("/api/sessions").json()
    assert body["total"] == 1
    item = body["items"][0]
    for field in (
        "session_uid", "started_at", "track_name", "session_type_name",
        "session_category", "num_laps", "best_lap_ms", "weather_name",
        "assists_summary", "ended_naturally", "end_reason", "loss_pct", "incomplete",
    ):
        assert field in item, f"missing {field} in the library row"
    assert item["track_name"] == "Interlagos"
    assert item["best_lap_ms"] == 71_439


def test_session_uid_is_a_string(client) -> None:
    """It is a uint64 on the wire, beyond what JSON handles without loss."""
    item = client.get("/api/sessions").json()["items"][0]
    assert isinstance(item["session_uid"], str)
    assert item["session_uid"] == REFERENCE_UID


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("track_id=16", 1),
        ("track_id=11", 0),
        ("session_category=race", 1),
        ("session_category=qualifying", 0),
        ("session_type=10", 1),
        ("from=2026-01-01", 1),
        ("from=2027-01-01", 0),
        ("to=2020-01-01", 0),
    ],
)
def test_filters(client, query: str, expected: int) -> None:
    assert client.get(f"/api/sessions?{query}").json()["total"] == expected


def test_pagination_shape(client) -> None:
    body = client.get("/api/sessions?limit=1&offset=0").json()
    assert body["limit"] == 1 and body["offset"] == 0
    assert client.get("/api/sessions?limit=1&offset=5").json()["items"] == []


def test_tracks(client) -> None:
    items = client.get("/api/tracks").json()["items"]
    assert items == [{"track_id": 16, "track_name": "Interlagos", "session_count": 1}]


# ---------------------------------------------------------------- session detail


def test_session_detail_carries_the_full_comparability_context(client) -> None:
    """FR-022. Both packets' assists, not just the Session packet's nine."""
    body = client.get(f"/api/sessions/{REFERENCE_UID}").json()
    assists = body["assists"]
    assert assists["steering"] == 0
    assert assists["gearbox"] == 1
    assert assists["traction_control"] == 2, "TC comes from CarStatus, not Session"
    assert assists["anti_lock_brakes"] == 1
    assert body["conditions"] == {
        "weather_name": "overcast", "air_temp_c": 24, "track_temp_c": 31
    }
    assert body["ai_difficulty"] == 90


def test_unknown_session_returns_the_documented_error_shape(client) -> None:
    response = client.get("/api/sessions/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


# ---------------------------------------------------------------- laps and stints


def test_laps_match_the_game(client) -> None:
    items = client.get(f"/api/sessions/{REFERENCE_UID}/laps").json()["items"]
    assert {lap["lap_number"]: lap["lap_time_ms"] for lap in items} == REFERENCE_LAPS


def test_every_lap_is_returned_with_its_exclusion_reason(client) -> None:
    """Not a pre-filtered list: the client must never re-derive validity."""
    items = client.get(f"/api/sessions/{REFERENCE_UID}/laps").json()["items"]
    assert len(items) == 5
    for lap in items:
        assert "counts" in lap and "exclusion_reason" in lap
        if not lap["counts"]:
            assert lap["exclusion_reason"], f"lap {lap['lap_number']} excluded without a reason"


def test_tyre_wear_is_named_per_wheel(client) -> None:
    """Never positional: F1 23 orders wheel arrays rear-left first."""
    lap = client.get(f"/api/sessions/{REFERENCE_UID}/laps").json()["items"][0]
    for wheel in ("rl", "rr", "fl", "fr"):
        assert f"tyre_wear_{wheel}" in lap


def test_stints(client) -> None:
    items = client.get(f"/api/sessions/{REFERENCE_UID}/stints").json()["items"]
    assert len(items) == 2
    assert (items[0]["start_lap"], items[0]["end_lap"]) == (1, 4)


def test_laps_for_an_unknown_session_are_a_404(client) -> None:
    assert client.get("/api/sessions/nope/laps").status_code == 404
    assert client.get("/api/sessions/nope/stints").status_code == 404


# ---------------------------------------------------------------- read-only


def test_the_api_exposes_no_write_routes(client) -> None:
    """A design property, not an omission: ingest owns the write path."""
    schema = client.get("/api/openapi.json").json()
    verbs = {
        method
        for path in schema["paths"].values()
        for method in path
        if method in {"post", "put", "patch", "delete"}
    }
    assert verbs == set(), f"unexpected write routes: {verbs}"
