"""T002, T003 -- participants and event details decoded from the reference capture.

Participants give the names behind the car indices; the event detail union turns fastest
laps, overtakes, speed traps and penalties into values that can be checked against the
session's own SessionHistory and against physical plausibility.
"""

from __future__ import annotations

from f1dc.wire.f1_2023 import OBSERVED_WIRE_SIZES
from f1dc.wire.f1_2023.event import EventCodec
from f1dc.wire.f1_2023.participants import ParticipantsCodec
from f1dc.wire.f1_2023.session_history import SessionHistoryCodec, SessionHistoryData
from tests.conftest import first_of

CARS = 20
#: The player's penalty events in the reference race sit on laps 1 and 4.
PLAYER_PENALTY_LAPS = {1, 4}


# --------------------------------------------------------------------------------------
# Participants (packet 4)
# --------------------------------------------------------------------------------------


def test_participants_decode_the_active_cars(by_packet_id, player_index) -> None:
    payload = first_of(by_packet_id, 4)
    assert ParticipantsCodec.num_active(payload) == CARS
    cars = ParticipantsCodec.decode_active(payload)
    assert len(cars) == CARS
    assert all(car.name for car in cars), "every active car should carry a name"

    player = ParticipantsCodec.decode_car(payload, player_index)
    assert player.name == "VERSTAPPEN"
    assert player.ai_controlled == 0


def test_participants_wire_size_matches_observed(by_packet_id) -> None:
    payload = first_of(by_packet_id, 4)
    assert ParticipantsCodec.wire_size == OBSERVED_WIRE_SIZES[4]
    assert len(payload) == OBSERVED_WIRE_SIZES[4]


# --------------------------------------------------------------------------------------
# Event detail (packet 3, decoded through EventData.parsed)
# --------------------------------------------------------------------------------------


def _events(by_packet_id):
    return [EventCodec.decode(r.payload) for r in by_packet_id.get(3, [])]


def _latest_session_history(by_packet_id) -> dict[int, SessionHistoryData]:
    latest: dict[int, SessionHistoryData] = {}
    for rec in by_packet_id.get(11, []):
        history = SessionHistoryCodec.decode(rec.payload)
        latest[history.car_idx] = history
    return latest


def test_fastest_lap_events_match_session_history(by_packet_id) -> None:
    latest = _latest_session_history(by_packet_id)
    ftlp = [e.parsed() for e in _events(by_packet_id) if e.code == "FTLP"]
    assert ftlp, "the reference race contains fastest-lap events"
    for event in ftlp:
        ms = round(event.value * 1000)
        recorded = [lap.lap_time_ms for lap in latest[event.vehicle_idx].laps if lap.is_recorded]
        assert any(abs(ms - t) <= 1 for t in recorded), (
            f"FTLP for car {event.vehicle_idx} reports {ms} ms, not in its session history"
        )


def test_overtake_events_reference_known_cars(by_packet_id) -> None:
    ovtk = [e.parsed() for e in _events(by_packet_id) if e.code == "OVTK"]
    assert ovtk
    for event in ovtk:
        assert 0 <= event.vehicle_idx < CARS
        assert 0 <= event.other_vehicle_idx < CARS


def test_speed_trap_speeds_are_plausible(by_packet_id) -> None:
    sptp = [e.parsed() for e in _events(by_packet_id) if e.code == "SPTP"]
    assert sptp
    for event in sptp:
        assert 50 <= event.value <= 400, f"speed trap {event.value} km/h out of range"


def test_player_penalties_are_on_laps_one_and_four(by_packet_id, player_index) -> None:
    pena = [
        p
        for p in (e.parsed() for e in _events(by_packet_id) if e.code == "PENA")
        if p.vehicle_idx == player_index
    ]
    assert len(pena) == 2
    assert {p.extra["lap_num"] for p in pena} == PLAYER_PENALTY_LAPS
