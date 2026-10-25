"""T013, T015 -- feature 003 car and race data, against SC-002's measured figures.

Figures the committed fixture preserves are asserted here. The rest -- tyre temperatures on
lap 3, whose telemetry the fixture does not keep -- are asserted on the full capture in
tests/integration/test_trace_precision.py.
"""

from __future__ import annotations

import pytest

from f1dc.analysis import car
from f1dc.analysis.compare import CompareError
from f1dc.ingest.car import OFF_TRACK
from tests.conftest import REFERENCE_UID


@pytest.fixture(scope="module")
def laps(ingested):
    return {row["lap_number"]: row for row in car.lap_car(ingested, REFERENCE_UID)}


# ---------------------------------------------------------------- energy (US2)


def test_the_battery_drains_across_the_race(laps) -> None:
    """SC-002: 3.9 MJ falling to under 0.2 MJ."""
    assert laps[1]["ers_start_mj"] == pytest.approx(3.91, abs=0.02)
    assert laps[5]["ers_end_mj"] < 0.2


def test_every_lap_ran_an_energy_deficit(laps) -> None:
    """Deployed exceeded harvested on every lap (FR-008)."""
    assert all(row["ers_balance_mj"] < 0 for row in laps.values())


def test_the_final_lap_energy_survives_the_reset_at_the_line(laps) -> None:
    """The counters reset after the chequered flag while the lap number holds; reading
    the last value gave 0.00 MJ deployed on lap 5 during design. The maximum does not."""
    assert laps[5]["ers_deployed_mj"] > 1.0


def test_fuel_is_used_every_lap(laps) -> None:
    assert all(0.5 < row["fuel_used_kg"] < 3 for row in laps.values())


# ---------------------------------------------------------------- settings and damage (US6)


def test_the_brake_bias_change_is_recorded_and_flagged(laps) -> None:
    """SC-002: 63% -> 57% on laps 3-4."""
    assert laps[2]["brake_bias"] == "63"
    assert laps[3]["brake_bias"] == "57,63"
    assert laps[3]["settings_changed"] is True
    assert laps[2]["settings_changed"] is False


def test_the_front_wing_damage_is_found(laps) -> None:
    """SC-002: 27% front-left wing damage, which nothing showed before this feature."""
    assert laps[3]["damage_front_left_wing"] == 0
    assert laps[4]["damage_front_left_wing"] == 27
    assert laps[4]["damage_increased"] is True


def test_the_mid_lap_tyre_change_is_flagged(laps) -> None:
    """R5: lap 4 is where the tyres were changed, so its aggregates stop at the change."""
    assert laps[4]["tyre_change_in_lap"] is True
    assert not any(laps[n]["tyre_change_in_lap"] for n in (1, 2, 3, 5))


# ---------------------------------------------------------------- track limits (US3)


def test_the_best_lap_had_no_excursions(laps) -> None:
    """SC-002: lap 2, the best lap, was the only clean racing lap."""
    assert laps[2]["excursions"] == 0


def test_kerbs_concrete_and_the_pit_lane_are_not_off_track() -> None:
    """FR-010. Surface ids: 1 rumble strip, 2 concrete, 10 metal (the pit lane)."""
    assert not {0, 1, 2, 10} & set(OFF_TRACK)
    assert set(OFF_TRACK.values()) == {"rock", "gravel", "mud", "sand", "grass"}


def test_excursions_are_located_on_the_lap(ingested) -> None:
    for ex in car.excursions(ingested, REFERENCE_UID):
        assert 0 <= ex["start_m"] <= 4294
        assert ex["surface"]
        assert ex["wheels"]


# ---------------------------------------------------------------- the field (US5)


def test_the_field_is_named_and_ranked(ingested) -> None:
    """SC-002: the best lap ranks 8th of 20; the fastest was 1:10.900."""
    field = car.field(ingested, REFERENCE_UID)
    assert field["ranked_count"] == 20
    assert field["player_rank"] == 8
    assert field["cars"][0]["best_lap_ms"] == 70_900
    assert field["cars"][0]["name"] == "PÉREZ", "non-ASCII names must decode as UTF-8"


def test_the_player_is_identified(ingested) -> None:
    player = [c for c in car.field(ingested, REFERENCE_UID)["cars"] if c["is_player"]]
    assert len(player) == 1
    assert player[0]["name"] == "VERSTAPPEN"
    assert player[0]["best_lap_ms"] == 71_439


def test_every_car_has_its_laps(ingested) -> None:
    field = car.field(ingested, REFERENCE_UID)
    with_laps = {row["car_idx"] for row in field["laps"]}
    assert with_laps == {c["car_idx"] for c in field["cars"] if c["num_laps"]}


# ---------------------------------------------------------------- timeline (US6)


def test_the_corner_cutting_warnings_are_events(ingested) -> None:
    """The two warnings found in feature 001, on laps 1 and 4."""
    events = car.timeline(ingested, REFERENCE_UID)["events"]
    penalties = [e for e in events if e["code"] == "PENA" and e["involves_player"]]
    assert [e["lap_number"] for e in penalties] == [1, 4]


def test_overtakes_name_both_drivers(ingested) -> None:
    events = car.timeline(ingested, REFERENCE_UID)["events"]
    overtakes = [e for e in events if e["code"] == "OVTK"]
    assert overtakes
    assert all(" overtook " in e["description"] for e in overtakes)
    assert sum(e["involves_player"] for e in overtakes) == 17


def test_conditions_are_recorded(ingested) -> None:
    conditions = car.timeline(ingested, REFERENCE_UID)["conditions"]
    assert conditions[0]["weather"] == "overcast"
    assert conditions[0]["track_temp_c"] == 31


def test_tyre_sets_carry_the_games_estimate(ingested) -> None:
    sets = car.tyre_sets(ingested, REFERENCE_UID)
    assert len(sets) == 20
    assert sum(s["fitted"] for s in sets) == 1
    assert all(isinstance(s["lap_delta_ms"], int) for s in sets)


# ---------------------------------------------------------------- availability


def test_a_session_from_before_1_2_0_says_so(ingested, tmp_path) -> None:
    """Never empty lists that read as 'no data' -- say re-ingest is needed."""
    import shutil

    from f1dc.config import Paths
    from f1dc.store import layout

    paths = Paths(tmp_path)
    paths.ensure()
    shutil.copytree(ingested.sessions_dir, paths.sessions_dir, dirs_exist_ok=True)
    (layout.session_dir(paths, REFERENCE_UID) / layout.LAP_CAR_FILE).unlink()

    with pytest.raises(CompareError) as exc:
        car.lap_car(paths, REFERENCE_UID)
    assert exc.value.code == "data_unavailable"
    assert "ingest" in exc.value.message


def test_the_players_stints_come_from_tyre_age_not_the_game(ingested) -> None:
    """The game says the player's first stint ended on lap 2; it ended on lap 4."""
    player = next(c for c in car.field(ingested, REFERENCE_UID)["cars"] if c["is_player"])
    assert player["stints"] == "Soft 1-4 · Soft 5-5"


def test_rival_stints_show_compounds_and_stops_not_wrong_end_laps(ingested) -> None:
    perez = next(c for c in car.field(ingested, REFERENCE_UID)["cars"] if c["name"] == "PÉREZ")
    assert perez["stints"] == "Soft → Soft (1 stop)"


def test_penalties_are_described_in_words(ingested) -> None:
    events = car.timeline(ingested, REFERENCE_UID)["events"]
    texts = [e["description"] for e in events if e["code"] == "PENA" and e["involves_player"]]
    assert texts == ["Warning: VERSTAPPEN -- corner cutting"] * 2


def test_a_zero_gap_in_the_pit_lane_is_not_a_gap(laps) -> None:
    assert laps[3]["gap_ahead_ms_at_line"] is None
