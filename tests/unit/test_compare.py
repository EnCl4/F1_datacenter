"""T016, T026, T029 -- comparison rules, the running time gap, and session pace."""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from f1dc.analysis.compare import (
    CompareError,
    LapRef,
    compare,
    differing_fields,
    laps_at_track,
    pace,
    running_gap,
)
from f1dc.config import Paths
from f1dc.store import layout
from tests.conftest import REFERENCE_LAPS, REFERENCE_UID

OTHER_UID = "11111111111111111111"


@pytest.fixture
def two_circuits(ingested: Paths, tmp_path: Path) -> Paths:
    """A copy of the store holding the reference race plus a fake Monza session."""
    paths = Paths(tmp_path)
    paths.ensure()
    shutil.copytree(ingested.sessions_dir, paths.sessions_dir, dirs_exist_ok=True)

    dst = layout.session_dir(paths, OTHER_UID)
    shutil.copytree(layout.session_dir(paths, REFERENCE_UID), dst)

    def replace(table: pa.Table, column: str, values: pa.Array) -> pa.Table:
        return table.set_column(table.schema.get_field_index(column), column, values)

    for name in (layout.SESSION_FILE, layout.LAPS_FILE, layout.STINTS_FILE, layout.TRACES_FILE):
        table = pq.read_table(dst / name)
        table = replace(table, "session_uid", pa.array([OTHER_UID] * table.num_rows))
        if name == layout.SESSION_FILE:
            table = replace(table, "track_id", pa.array([11], pa.int16()))
            table = replace(table, "track_name", pa.array(["Monza"]))
        pq.write_table(table, dst / name)
    return paths


# ---------------------------------------------------------------- lap references


def test_lap_refs_parse() -> None:
    assert LapRef.parse(f"{REFERENCE_UID}:2") == LapRef(REFERENCE_UID, 2)


@pytest.mark.parametrize("bad", ["", "abc", "123", "123:", ":2", "12:x"])
def test_bad_lap_refs_are_rejected(bad: str) -> None:
    with pytest.raises(CompareError) as exc:
        LapRef.parse(bad)
    assert exc.value.code == "bad_lap_ref" and exc.value.status == 400


# ---------------------------------------------------------------- comparing


def test_comparison_of_laps_5_and_2(ingested: Paths) -> None:
    result = compare(ingested, f"{REFERENCE_UID}:5", f"{REFERENCE_UID}:2")
    assert result["lap"]["lap_number"] == 5
    assert result["reference"]["lap_number"] == 2
    assert len(result["gap"]["gap_ms"]) == 4295


def test_the_gap_at_the_line_is_the_lap_time_difference(ingested: Paths) -> None:
    """SC-002, on the committed fixture. The precision suite repeats this at full rate."""
    gap = compare(ingested, f"{REFERENCE_UID}:5", f"{REFERENCE_UID}:2")["gap"]["gap_ms"]
    assert gap[-1] == REFERENCE_LAPS[5] - REFERENCE_LAPS[2]  # +1203 ms
    assert gap[0] == 0


def test_the_reference_defaults_to_the_best_counting_lap(ingested: Paths) -> None:
    """FR-018: lap 2 is the reference race's only counting lap."""
    result = compare(ingested, f"{REFERENCE_UID}:5")
    assert result["reference"]["lap_number"] == 2


def test_different_circuits_are_refused(two_circuits: Paths) -> None:
    """FR-008, SC-008: metre 2 300 at Monza is not metre 2 300 at Interlagos."""
    with pytest.raises(CompareError) as exc:
        compare(two_circuits, f"{REFERENCE_UID}:5", f"{OTHER_UID}:2")
    assert exc.value.code == "different_circuits"
    assert exc.value.status == 409
    assert "Interlagos" in exc.value.message and "Monza" in exc.value.message


def test_a_lap_without_a_trace_explains_why(ingested: Paths) -> None:
    """FR-006: the fixture has no channel data for lap 3."""
    with pytest.raises(CompareError) as exc:
        compare(ingested, f"{REFERENCE_UID}:3", f"{REFERENCE_UID}:2")
    assert exc.value.code == "trace_unavailable"
    assert "lap 3" in exc.value.message.lower()


def test_an_unknown_lap_is_a_404(ingested: Paths) -> None:
    with pytest.raises(CompareError) as exc:
        compare(ingested, f"{REFERENCE_UID}:99", f"{REFERENCE_UID}:2")
    assert exc.value.status == 404


def test_a_non_counting_lap_can_be_compared_but_is_marked(ingested: Paths) -> None:
    """FR-015: lap 5 is an out lap."""
    result = compare(ingested, f"{REFERENCE_UID}:5", f"{REFERENCE_UID}:2")
    assert result["lap"]["counts"] is False
    assert result["lap"]["exclusion_reason"] == "out_lap"
    assert result["context"]["lap"]["counts"] is False


# ---------------------------------------------------------------- context


def test_context_shows_both_laps_and_lists_what_differs(ingested: Paths) -> None:
    ctx = compare(ingested, f"{REFERENCE_UID}:5", f"{REFERENCE_UID}:2")["context"]
    assert ctx["lap"]["assists_summary"] == ctx["reference"]["assists_summary"]
    # Both laps START on one-lap-old softs: lap 5's set went on mid-lap 4. What does
    # differ is fuel -- lap 5 carries three laps less, which the comparison must flag.
    assert ctx["lap"]["tyre_age_laps"] == ctx["reference"]["tyre_age_laps"] == 1
    assert ctx["differs"] == ["fuel_in_tank_start"]
    assert ctx["lap"]["fuel_in_tank_start"] < ctx["reference"]["fuel_in_tank_start"]


def test_fuel_within_a_kilogram_is_not_a_difference() -> None:
    a = {"fuel_in_tank_start": 10.0}
    assert "fuel_in_tank_start" not in differing_fields(a, {"fuel_in_tank_start": 10.6})
    assert "fuel_in_tank_start" in differing_fields(a, {"fuel_in_tank_start": 12.0})


# ---------------------------------------------------------------- the gap itself


def test_gap_is_positive_when_behind() -> None:
    lap = {"distance_m": [0, 1, 2], "time_ms": [0.0, 12.0, 25.0]}
    ref = {"distance_m": [0, 1, 2], "time_ms": [0.0, 10.0, 20.0]}
    assert running_gap(lap, ref)["gap_ms"] == [0.0, 2.0, 5.0]


def test_gap_is_null_where_either_lap_has_a_gap() -> None:
    lap = {"distance_m": [0, 1, 2], "time_ms": [0.0, None, 25.0]}
    ref = {"distance_m": [0, 1, 2], "time_ms": [0.0, 10.0, None]}
    assert running_gap(lap, ref)["gap_ms"] == [0.0, None, None]


def test_gap_covers_only_the_shared_distance() -> None:
    lap = {"distance_m": [0, 1, 2, 3], "time_ms": [0.0, 1.0, 2.0, 3.0]}
    ref = {"distance_m": [0, 1], "time_ms": [0.0, 1.0]}
    assert running_gap(lap, ref)["distance_m"] == [0, 1]


# ---------------------------------------------------------------- pace and lap lists


def test_pace_lists_every_lap_and_stint(ingested: Paths) -> None:
    data = pace(ingested, REFERENCE_UID)
    assert [lap["lap_number"] for lap in data["laps"]] == [1, 2, 3, 4, 5]
    assert {lap["lap_number"]: lap["lap_time_ms"] for lap in data["laps"]} == REFERENCE_LAPS
    assert [(s["start_lap"], s["end_lap"]) for s in data["stints"]] == [(1, 4), (5, 5)]
    assert [lap["counts"] for lap in data["laps"]] == [False, True, False, False, False]


def test_laps_at_track_mark_which_have_traces(ingested: Paths) -> None:
    rows = laps_at_track(ingested, 16)
    traced = {r["lap_number"] for r in rows if r["has_trace"]}
    assert len(rows) == 5
    assert {2, 5} <= traced
    assert 3 not in traced


def test_laps_at_another_track_are_not_listed(ingested: Paths) -> None:
    assert laps_at_track(ingested, 11) == []
