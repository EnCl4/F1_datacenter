"""T070 -- the reference race, end to end.

Known-good figures from a real five-lap race at Interlagos on 2026-09-04. If any of these
change, either the game changed or we broke something -- and either way we want to know
before it reaches a season of recorded data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from f1dc.config import Paths
from f1dc.ingest.pipeline import run_ingest
from f1dc.store import catalog
from tests.conftest import REFERENCE, REFERENCE_LAPS, REFERENCE_UID

EXPECTED_EXCLUSIONS = {
    1: "first_lap",
    2: None,
    3: "pit",
    4: "pit",
    5: "out_lap",
}


def test_session_metadata(ingested) -> None:
    session = catalog.get_session(ingested, REFERENCE_UID)
    assert session is not None
    assert session["track_name"] == REFERENCE["track_name"]
    assert session["track_length_m"] == REFERENCE["track_length"]
    assert session["session_type_name"] == "Race"
    assert session["session_category"] == "race"
    assert session["total_laps"] == 5
    assert session["weather_name"] == "overcast"
    assert session["track_temp_c"] == 31
    assert session["air_temp_c"] == 24
    assert session["ai_difficulty"] == 90
    assert session["player_car_index"] == 19


def test_the_race_ended_at_the_chequered_flag(ingested) -> None:
    session = catalog.get_session(ingested, REFERENCE_UID)
    assert session["end_reason"] == "chequered"
    assert session["ended_naturally"] is True


def test_all_five_lap_times(ingested) -> None:
    laps = catalog.get_laps(ingested, REFERENCE_UID)
    assert {lap["lap_number"]: lap["lap_time_ms"] for lap in laps} == REFERENCE_LAPS


def test_exclusion_reasons(ingested) -> None:
    laps = {lap["lap_number"]: lap for lap in catalog.get_laps(ingested, REFERENCE_UID)}
    assert {n: laps[n]["exclusion_reason"] for n in laps} == EXPECTED_EXCLUSIONS


def test_only_lap_two_counts(ingested) -> None:
    session = catalog.get_session(ingested, REFERENCE_UID)
    assert session["num_laps"] == 5
    assert session["num_counting_laps"] == 1
    assert session["best_lap_ms"] == 71_439
    assert session["best_lap_number"] == 2


def test_the_pit_stop_shows_its_real_cost(ingested) -> None:
    """Lap 4 at 90.6 s is the stop. If lap times were misattributed it would read 72.6."""
    laps = {lap["lap_number"]: lap for lap in catalog.get_laps(ingested, REFERENCE_UID)}
    assert laps[4]["lap_time_ms"] == 90_600
    assert laps[4]["lap_time_ms"] - laps[2]["lap_time_ms"] > 15_000


def test_assists_come_from_both_packets(ingested) -> None:
    session = catalog.get_session(ingested, REFERENCE_UID)
    assert session["assist_steering"] == 0
    assert session["assist_braking"] == 0
    assert session["assist_gearbox"] == 1
    assert session["assist_traction_control"] == 2
    assert session["assist_anti_lock_brakes"] == 1
    assert "TC" in session["assists_summary"]


def test_two_stints_soft_throughout(ingested) -> None:
    stints = catalog.get_stints(ingested, REFERENCE_UID)
    assert len(stints) == 2
    assert all(s["tyre_visual_compound_name"] == "Soft" for s in stints)
    assert all(s["tyre_actual_compound_name"] == "C4" for s in stints)


def test_tyre_wear_is_recorded_per_wheel(ingested) -> None:
    laps = catalog.get_laps(ingested, REFERENCE_UID)
    for lap in laps:
        for wheel in ("rl", "rr", "fl", "fr"):
            wear = lap[f"tyre_wear_{wheel}"]
            assert wear is None or 0.0 <= wear <= 100.0


def test_no_data_quality_flags_were_raised(ingested) -> None:
    for lap in catalog.get_laps(ingested, REFERENCE_UID):
        assert lap["sector_sum_mismatch"] is False
        assert lap["history_mismatch"] is False


# ---------------------------------------------------------------- the full capture


@pytest.mark.needs_full_capture
@pytest.mark.slow
def test_the_full_capture_reproduces_everything(request, tmp_path: Path) -> None:
    """Same assertions against the complete 229 MB capture, not the curated slice.

    Run with:  pytest --raw C:/F1Data/raw/<capture>.f1raw
    """
    raw = request.config.getoption("--raw")
    if not raw or not Path(raw).exists():
        pytest.skip("no --raw capture supplied")

    import shutil

    paths = Paths(tmp_path)
    paths.ensure()
    shutil.copy(raw, paths.raw_dir / "2026-09-04T11-04-12_15975277775803518192.f1raw")
    assert run_ingest(paths, compress_logs=False) == 0

    laps = catalog.get_laps(paths, REFERENCE_UID)
    assert {lap["lap_number"]: lap["lap_time_ms"] for lap in laps} == REFERENCE_LAPS

    session = catalog.get_session(paths, REFERENCE_UID)
    assert session["best_lap_ms"] == 71_439
    # The full capture is not subsampled, so its loss should be the measured baseline.
    assert session["loss_pct"] < 0.5, f"unexpected loss {session['loss_pct']}%"
