"""T045 -- lap splitting, and the three defects found against real bytes.

These are regression tests for actual mistakes made during development, not hypothetical
edge cases:

1. ``m_lastLapTimeInMS`` attributed to the wrong lap.
2. Sector times read from the millisecond field alone, wrapping above 65.535 s.
3. Stints derived from ``SessionHistory.m_tyreStintsEndLaps``, which disagrees with the
   pit-stop evidence in the reference capture.
"""

from __future__ import annotations

from f1dc.store import catalog
from f1dc.wire.f1_2023.lap_data import combine_sector
from tests.conftest import REFERENCE_LAPS, REFERENCE_UID


# ---------------------------------------------------------------- sector recombination


def test_sector_recombination_below_the_ceiling() -> None:
    assert combine_sector(17_204, 0) == 17_204


def test_sector_recombination_at_and_past_the_ceiling() -> None:
    """A uint16 saturates at 65 535; the minutes field carries the overflow."""
    assert combine_sector(5_535, 1) == 65_535
    assert combine_sector(10_000, 1) == 70_000
    assert combine_sector(30_000, 2) == 150_000


# ---------------------------------------------------------------- lap times


def test_every_lap_time_matches_the_game(ingested) -> None:
    """The whole point: our lap table equals what F1 23 itself reported."""
    laps = catalog.get_laps(ingested, REFERENCE_UID)
    actual = {lap["lap_number"]: lap["lap_time_ms"] for lap in laps}
    assert actual == REFERENCE_LAPS


def test_lap_time_is_not_attributed_to_the_previous_lap(ingested) -> None:
    """The off-by-one that produced a plausible but wrong lap table on the first pass.

    Lap 4 is the pit lap at 90.600 s. If ``m_lastLapTimeInMS`` were attributed to the lap
    reporting it, lap 4 would show 72.642 -- lap 5's time -- and the pit stop would vanish
    from the data entirely.
    """
    laps = {lap["lap_number"]: lap for lap in catalog.get_laps(ingested, REFERENCE_UID)}
    assert laps[4]["lap_time_ms"] == 90_600, "lap 4 is the pit lap and must show its real cost"
    assert laps[5]["lap_time_ms"] == 72_642


def test_the_final_lap_has_a_time(ingested) -> None:
    """After the chequered flag the game keeps currentLapNum at the final lap while
    reporting that lap's own time, so naive attribution loses the last lap entirely."""
    laps = {lap["lap_number"]: lap for lap in catalog.get_laps(ingested, REFERENCE_UID)}
    assert laps[max(laps)]["lap_time_ms"] is not None


def test_sectors_sum_to_the_lap_time(ingested) -> None:
    for lap in catalog.get_laps(ingested, REFERENCE_UID):
        if not all([lap["lap_time_ms"], lap["sector1_ms"], lap["sector2_ms"], lap["sector3_ms"]]):
            continue
        total = lap["sector1_ms"] + lap["sector2_ms"] + lap["sector3_ms"]
        assert abs(total - lap["lap_time_ms"]) <= 5, f"lap {lap['lap_number']} sectors disagree"
        assert lap["sector_sum_mismatch"] is False


def test_lap_times_agree_between_sources(ingested) -> None:
    """T051: LapData-derived and SessionHistory times must agree, not be silently picked."""
    for lap in catalog.get_laps(ingested, REFERENCE_UID):
        assert lap["history_mismatch"] is False, f"lap {lap['lap_number']} sources disagree"


# ---------------------------------------------------------------- stints


def test_stints_follow_the_pit_evidence_not_the_history_field(ingested) -> None:
    """SessionHistory says the first stint ended on lap 2. Tyre age (3 -> 0 during lap 4)
    and numPitStops (0 -> 1 on lap 4) both say lap 4. The evidence wins.
    """
    stints = catalog.get_stints(ingested, REFERENCE_UID)
    assert len(stints) == 2, f"expected two stints, got {len(stints)}"

    first, second = stints
    assert (first["start_lap"], first["end_lap"]) == (1, 4), (
        "the pit lap belongs to the outgoing stint"
    )
    assert second["start_lap"] == 5


def test_every_lap_is_assigned_to_a_stint(ingested) -> None:
    laps = catalog.get_laps(ingested, REFERENCE_UID)
    assert all(lap["stint_index"] is not None for lap in laps)
    assert {lap["stint_index"] for lap in laps} == {0, 1}


def test_tyre_age_increases_within_a_stint_and_resets_across_one(ingested) -> None:
    laps = {lap["lap_number"]: lap for lap in catalog.get_laps(ingested, REFERENCE_UID)}
    assert [laps[n]["tyre_age_laps"] for n in (1, 2, 3, 4)] == [0, 1, 2, 3]
    assert laps[5]["tyre_age_laps"] < laps[4]["tyre_age_laps"], "new tyres were fitted"
