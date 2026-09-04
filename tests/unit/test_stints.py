"""T069 -- stint derivation.

Stints come from tyre-age evidence, not from ``SessionHistory.m_tyreStintsEndLaps``.
That field proved unreliable against the reference capture: it reports the player's first
stint ending on lap 2, while tyre age (3 -> 0 during lap 4) and ``numPitStops`` (0 -> 1 on
lap 4) both say lap 4, and another car in the same race reports ``endLap = 0``.
"""

from __future__ import annotations

from f1dc.ingest.laps import build_stints, stint_for_lap
from f1dc.ingest.sessionizer import LapContext, RawSession


def session_with(ages: list[int], compounds: list[int] | None = None) -> RawSession:
    """A session whose laps have the given tyre age at their start."""
    raw = RawSession(session_uid=1, player_index=19)
    compounds = compounds or [17] * len(ages)
    for index, (age, compound) in enumerate(zip(ages, compounds, strict=True), start=1):
        ctx = LapContext(lap_number=index, first_seen=0.0, last_seen=0.0)
        ctx.tyre_age = age
        ctx.tyre_actual = compound
        ctx.tyre_visual = 16
        ctx._status_seen = True
        raw.laps[index] = ctx
    raw.events = ["CHQF"]
    return raw


def test_a_session_with_no_stop_is_one_stint() -> None:
    stints = build_stints("1", session_with([0, 1, 2, 3, 4]))
    assert len(stints) == 1
    assert (stints[0].start_lap, stints[0].end_lap) == (1, 5)


def test_a_tyre_age_reset_starts_a_new_stint() -> None:
    """The reference race exactly: ages 0,1,2,3 then 1 after the stop on lap 4."""
    stints = build_stints("1", session_with([0, 1, 2, 3, 1]))
    assert len(stints) == 2
    assert (stints[0].start_lap, stints[0].end_lap) == (1, 4)
    assert (stints[1].start_lap, stints[1].end_lap) == (5, 5)


def test_the_pit_lap_belongs_to_the_outgoing_stint() -> None:
    """How a stop is normally described: "he pitted on lap 4, first stint laps 1-4"."""
    stints = build_stints("1", session_with([0, 1, 2, 3, 1]))
    assert stints[0].end_lap == 4
    assert stint_for_lap(stints, 4) == 0
    assert stint_for_lap(stints, 5) == 1


def test_a_compound_change_starts_a_new_stint_even_without_an_age_drop() -> None:
    stints = build_stints("1", session_with([0, 1, 0, 1], compounds=[17, 17, 18, 18]))
    assert len(stints) == 2
    assert stints[1].tyre_actual_compound == 18


def test_two_stops_give_three_stints() -> None:
    stints = build_stints("1", session_with([0, 1, 2, 0, 1, 2, 0, 1]))
    assert [(s.start_lap, s.end_lap) for s in stints] == [(1, 3), (4, 6), (7, 8)]


def test_num_laps_is_consistent_with_the_boundaries() -> None:
    for stint in build_stints("1", session_with([0, 1, 2, 3, 1])):
        assert stint.num_laps == (stint.end_lap or 0) - stint.start_lap + 1


def test_an_unfinished_session_leaves_the_last_stint_open() -> None:
    raw = session_with([0, 1, 2, 3, 1])
    raw.events = []  # no chequered flag: the session was abandoned
    stints = build_stints("1", raw)
    assert stints[-1].end_lap is None


def test_laps_without_car_status_are_ignored() -> None:
    """A lap we never saw tyre data for cannot be evidence of anything."""
    raw = session_with([0, 1])
    orphan = LapContext(lap_number=3, first_seen=0.0, last_seen=0.0)
    raw.laps[3] = orphan  # _status_seen stays False
    stints = build_stints("1", raw)
    assert len(stints) == 1


def test_a_session_with_no_usable_laps_has_no_stints() -> None:
    assert build_stints("1", RawSession(session_uid=1, player_index=0)) == []


def test_stint_lookup_returns_none_outside_any_stint() -> None:
    stints = build_stints("1", session_with([0, 1]))
    assert stint_for_lap(stints, 99) is None
