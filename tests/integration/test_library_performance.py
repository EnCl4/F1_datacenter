"""T084 -- SC-007: the library stays responsive at 500+ sessions.

The library is the feature whose value compounds. Five sessions is mildly interesting;
five hundred is the reason the product exists -- so it has to still be usable there.

Sessions are synthesised directly into the store rather than driven, because what is
being measured is the query path, not ingest.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
import pytest

from f1dc.config import Paths
from f1dc.ingest import INGEST_VERSION
from f1dc.store import catalog, layout
from f1dc.store.schema import LAP_SCHEMA, SESSION_SCHEMA, STINT_SCHEMA, table_from_rows

SESSION_COUNT = 500
LAPS_PER_SESSION = 20
LIST_BUDGET_SECONDS = 2.0

TRACKS = [(16, "Interlagos"), (11, "Monza"), (5, "Monaco"), (10, "Spa"), (29, "Jeddah")]
CATEGORIES = ["race", "qualifying", "practice", "time_trial"]


def _session_row(index: int) -> dict:
    track_id, track_name = TRACKS[index % len(TRACKS)]
    started = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index * 7)
    return {
        "session_uid": f"{10_000_000_000_000_000 + index}",
        "recording_id": f"rec-{index}",
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(minutes=30)).isoformat(),
        "duration_s": 1800.0,
        "track_id": track_id,
        "track_name": track_name,
        "track_length_m": 4300,
        "session_type": 10,
        "session_type_name": "Race",
        "session_category": CATEGORIES[index % len(CATEGORIES)],
        "total_laps": LAPS_PER_SESSION,
        "weather": 2,
        "weather_name": "overcast",
        "air_temp_c": 24,
        "track_temp_c": 31,
        "ai_difficulty": 90,
        "formula": 0,
        "game_mode": 0,
        "rule_set": 0,
        "network_game": False,
        "player_car_index": 19,
        "ended_naturally": True,
        "end_reason": "chequered",
        "started_late": False,
        "num_laps": LAPS_PER_SESSION,
        "num_counting_laps": LAPS_PER_SESSION - 2,
        "best_lap_ms": 71_000 + (index % 900),
        "best_lap_number": 4,
        "loss_pct": 0.2,
        "ingest_version": INGEST_VERSION,
        "assist_steering": 0, "assist_braking": 0, "assist_gearbox": 1,
        "assist_pit": 0, "assist_pit_release": 1, "assist_ers": 0, "assist_drs": 0,
        "assist_racing_line": 0, "assist_racing_line_type": 0,
        "assist_traction_control": 2, "assist_anti_lock_brakes": 1,
        "assists_summary": "TC full, ABS, manual gearbox",
        "incomplete": False,
    }


def _lap_rows(uid: str) -> list[dict]:
    return [
        {
            "session_uid": uid, "lap_number": n, "stint_index": 0,
            "lap_time_ms": 71_000 + n * 13, "sector1_ms": 17_500,
            "sector2_ms": 36_900, "sector3_ms": 16_900,
            "valid": True, "sector1_valid": True, "sector2_valid": True,
            "sector3_valid": True, "counts": n > 1, "exclusion_reason": None if n > 1 else "first_lap",
            "is_in_lap": False, "is_out_lap": False, "pit_status": 0,
            "num_pit_stops": 0, "under_safety_car": False,
            "tyre_actual_compound": 17, "tyre_actual_compound_name": "C4",
            "tyre_visual_compound": 16, "tyre_visual_compound_name": "Soft",
            "tyre_age_laps": n, "fuel_in_tank_start": 40.0, "fuel_remaining_laps": 5.0,
            "tyre_wear_rl": 1.0, "tyre_wear_rr": 1.0, "tyre_wear_fl": 1.0, "tyre_wear_fr": 1.0,
            "car_position": 2, "penalties_s": 0, "corner_cutting_warnings": 0,
            "sector_sum_mismatch": False, "history_mismatch": False,
        }
        for n in range(1, LAPS_PER_SESSION + 1)
    ]


@pytest.fixture(scope="module")
def big_store(tmp_path_factory) -> Paths:
    paths = Paths(tmp_path_factory.mktemp("big-library"))
    paths.ensure()
    for index in range(SESSION_COUNT):
        row = _session_row(index)
        uid = row["session_uid"]
        directory = layout.session_dir(paths, uid)
        directory.mkdir(parents=True, exist_ok=True)
        pq.write_table(
            table_from_rows([row], SESSION_SCHEMA), directory / layout.SESSION_FILE,
            compression="zstd",
        )
        pq.write_table(
            table_from_rows(_lap_rows(uid), LAP_SCHEMA), directory / layout.LAPS_FILE,
            compression="zstd",
        )
        pq.write_table(
            table_from_rows([], STINT_SCHEMA), directory / layout.STINTS_FILE,
            compression="zstd",
        )
    return paths


@pytest.mark.slow
def test_the_store_really_has_five_hundred_sessions(big_store: Paths) -> None:
    assert catalog.session_count(big_store) == SESSION_COUNT


@pytest.mark.slow
def test_listing_stays_under_two_seconds(big_store: Paths) -> None:
    """SC-007."""
    start = time.perf_counter()
    total, items = catalog.list_sessions(big_store, limit=50)
    elapsed = time.perf_counter() - start

    assert total == SESSION_COUNT
    assert len(items) == 50
    assert elapsed < LIST_BUDGET_SECONDS, f"library listing took {elapsed:.2f}s"


@pytest.mark.slow
def test_filtered_listing_stays_under_two_seconds(big_store: Paths) -> None:
    start = time.perf_counter()
    total, _items = catalog.list_sessions(big_store, track_id=16, session_category="race")
    elapsed = time.perf_counter() - start
    assert total > 0
    assert elapsed < LIST_BUDGET_SECONDS, f"filtered listing took {elapsed:.2f}s"


@pytest.mark.slow
def test_opening_one_session_is_fast(big_store: Paths) -> None:
    """Detail must not degrade as the library grows -- it reads one directory."""
    uid = _session_row(250)["session_uid"]
    start = time.perf_counter()
    session = catalog.get_session(big_store, uid)
    laps = catalog.get_laps(big_store, uid)
    elapsed = time.perf_counter() - start

    assert session is not None
    assert len(laps) == LAPS_PER_SESSION
    assert elapsed < LIST_BUDGET_SECONDS, f"opening a session took {elapsed:.2f}s"


@pytest.mark.slow
def test_most_recent_first_ordering_holds_at_scale(big_store: Paths) -> None:
    _total, items = catalog.list_sessions(big_store, limit=10)
    dates = [item["started_at"] for item in items]
    assert dates == sorted(dates, reverse=True)
