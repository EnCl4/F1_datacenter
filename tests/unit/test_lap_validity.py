"""T046 -- the validity rule branches by session type.

Constitution principle VI. The branch is not a nicety: the reference race recorded zero
invalidated laps across all 22 cars while the player took two corner-cutting warnings and
a penalty. Races penalise; they do not invalidate. A single rule would call every race
lap clean, including cut corners, and manufacture false personal bests.
"""

from __future__ import annotations

import pytest

from f1dc.ingest.validity import best_lap, evaluate
from f1dc.models import (
    EXCLUSION_FIRST_LAP,
    EXCLUSION_INCOMPLETE,
    EXCLUSION_INVALIDATED,
    EXCLUSION_IN_LAP,
    EXCLUSION_OUT_LAP,
    EXCLUSION_PIT,
    EXCLUSION_SAFETY_CAR,
    Lap,
)
from f1dc.store import catalog
from f1dc.wire.f1_2023.enums import PRACTICE, QUALIFYING, RACE, TIME_TRIAL
from tests.conftest import REFERENCE_UID


def check(category: str, **overrides):
    kwargs = dict(
        session_category=category,
        lap_number=5,
        lap_time_ms=71_439,
        valid=True,
        is_in_lap=False,
        is_out_lap=False,
        pit_status=0,
        under_safety_car=False,
    )
    kwargs.update(overrides)
    return evaluate(**kwargs)


# ---------------------------------------------------------------- the branch itself


@pytest.mark.parametrize("category", [PRACTICE, QUALIFYING, TIME_TRIAL])
def test_flag_driven_categories_honour_the_invalidation_flag(category: str) -> None:
    assert check(category) == (True, None)
    assert check(category, valid=False) == (False, EXCLUSION_INVALIDATED)


def test_a_race_ignores_the_invalidation_flag(category=RACE) -> None:
    """THE case. In a race the flag is essentially never set, so relying on it would
    mark a cut-corner lap clean."""
    assert check(category, valid=False) == (True, None)


def test_a_race_excludes_the_first_lap(category=RACE) -> None:
    """A standing start makes lap 1 incomparable with any other lap."""
    assert check(category, lap_number=1) == (False, EXCLUSION_FIRST_LAP)


def test_qualifying_does_not_exclude_the_first_lap() -> None:
    assert check(QUALIFYING, lap_number=1) == (True, None)


def test_a_race_excludes_safety_car_laps(category=RACE) -> None:
    assert check(category, under_safety_car=True) == (False, EXCLUSION_SAFETY_CAR)


# ---------------------------------------------------------------- shared exclusions


@pytest.mark.parametrize("category", [PRACTICE, QUALIFYING, RACE, TIME_TRIAL])
def test_pit_involvement_excludes_in_every_category(category: str) -> None:
    assert check(category, pit_status=1) == (False, EXCLUSION_PIT)
    assert check(category, is_in_lap=True) == (False, EXCLUSION_IN_LAP)
    assert check(category, is_out_lap=True) == (False, EXCLUSION_OUT_LAP)


def test_pit_status_outranks_driver_status() -> None:
    """The reference pit lap reports in-lap AND out-lap status within one lap. Calling it
    an out lap would describe it wrongly -- it is the pit lap."""
    assert check(RACE, pit_status=2, is_in_lap=True, is_out_lap=True) == (False, EXCLUSION_PIT)


@pytest.mark.parametrize("category", [PRACTICE, QUALIFYING, RACE, TIME_TRIAL])
def test_an_incomplete_lap_never_counts(category: str) -> None:
    assert check(category, lap_time_ms=None) == (False, EXCLUSION_INCOMPLETE)
    assert check(category, lap_time_ms=0) == (False, EXCLUSION_INCOMPLETE)


def test_an_unknown_category_is_conservative() -> None:
    """Better to omit a lap than to invent a personal best."""
    assert check("unknown", valid=False) == (False, EXCLUSION_INVALIDATED)


# ---------------------------------------------------------------- personal bests


def _lap(number: int, time_ms: int, counts: bool) -> Lap:
    return Lap(
        session_uid="1", lap_number=number, stint_index=0, lap_time_ms=time_ms,
        sector1_ms=None, sector2_ms=None, sector3_ms=None, valid=True,
        sector1_valid=True, sector2_valid=True, sector3_valid=True,
        counts=counts, exclusion_reason=None, is_in_lap=False, is_out_lap=False,
        pit_status=0, num_pit_stops=0, under_safety_car=False,
        tyre_actual_compound=17, tyre_actual_compound_name="C4",
        tyre_visual_compound=16, tyre_visual_compound_name="Soft", tyre_age_laps=1,
        fuel_in_tank_start=None, fuel_remaining_laps=None,
        tyre_wear_rl=None, tyre_wear_rr=None, tyre_wear_fl=None, tyre_wear_fr=None,
        car_position=1, penalties_s=0, corner_cutting_warnings=0,
    )


def test_a_non_counting_lap_is_never_a_personal_best() -> None:
    """FR-024, SC-008. The fastest lap here does not count, so it must not be returned."""
    laps = [_lap(1, 60_000, counts=False), _lap(2, 71_439, counts=True)]
    assert best_lap(laps) == (71_439, 2)


def test_best_lap_is_none_when_nothing_counts() -> None:
    assert best_lap([_lap(1, 60_000, counts=False)]) == (None, None)


# ---------------------------------------------------------------- against real data


def test_the_reference_race_excludes_what_it_should(ingested) -> None:
    laps = {lap["lap_number"]: lap for lap in catalog.get_laps(ingested, REFERENCE_UID)}
    assert laps[1]["exclusion_reason"] == EXCLUSION_FIRST_LAP
    assert laps[2]["counts"] is True
    assert laps[3]["exclusion_reason"] == EXCLUSION_PIT
    assert laps[4]["exclusion_reason"] == EXCLUSION_PIT
    assert laps[5]["exclusion_reason"] == EXCLUSION_OUT_LAP


def test_the_reference_best_lap_is_the_only_counting_lap(ingested) -> None:
    _total, items = catalog.list_sessions(ingested)
    session = items[0]
    assert session["best_lap_ms"] == 71_439
    assert session["best_lap_number"] == 2
    assert session["num_counting_laps"] == 1


def test_no_lap_was_invalidated_in_the_reference_race(ingested) -> None:
    """The finding that forced the branch. Every race lap is 'valid' by the game's flag."""
    laps = catalog.get_laps(ingested, REFERENCE_UID)
    assert all(lap["valid"] for lap in laps)
    assert any(not lap["counts"] for lap in laps), "yet most of them should not count"
