"""T034 -- trace precision on full-rate data (SC-002, SC-003).

The committed fixture keeps every 10th frame, which tests structure but not precision. These
run against the complete reference capture:

    pytest tests/integration/test_trace_precision.py --raw C:/F1Data/raw/<capture>.f1raw

**How SC-003 is measured.** The spec phrases it as "a braking point lands within 5 m on
two laps". But braking points move because the driver brakes in different places -- on
the reference race, 2 218 / 2 230 / 2 216 m at one corner, a spread that is driving, not
alignment error. What alignment actually promises is that metre *n* is the same place on
the circuit on both laps, so it is measured by the car's world position at the same
metre. Measured on laps 2 and 5: median 1.0 m, 95th percentile 3.9 m.
"""

from __future__ import annotations

import itertools
import math
import shutil
import statistics
from pathlib import Path

import pytest

from f1dc.config import Paths
from f1dc.ingest.pipeline import run_ingest
from f1dc.store import catalog
from tests.conftest import FIXTURE_LOG_NAME, REFERENCE_LAPS, REFERENCE_UID

pytestmark = [pytest.mark.needs_full_capture, pytest.mark.slow]

#: Laps driven entirely on the racing line. Laps 3 and 4 include the pit lane, which is a
#: physically different path, so their positions legitimately diverge from these.
RACING_LAPS = (2, 5)


@pytest.fixture(scope="module")
def full(request, tmp_path_factory) -> Paths:
    raw = request.config.getoption("--raw")
    if not raw or not Path(raw).exists():
        pytest.skip("no --raw capture supplied")
    paths = Paths(tmp_path_factory.mktemp("full-capture"))
    paths.ensure()
    shutil.copy(raw, paths.raw_dir / FIXTURE_LOG_NAME)
    assert run_ingest(paths, compress_logs=False) == 0
    return paths


def test_every_lap_has_a_complete_trace(full: Paths) -> None:
    for lap in (2, 3, 4, 5):
        trace = catalog.get_trace(full, REFERENCE_UID, lap)
        assert trace is not None and len(trace["distance_m"]) == 4295
        assert sum(v is None for v in trace["speed_kph"]) == 0


@pytest.mark.parametrize(("a", "b"), list(itertools.combinations((1, 2, 3, 4, 5), 2)))
def test_gap_at_the_line_is_within_50_ms(full: Paths, a: int, b: int) -> None:
    """SC-002, for every pair of laps in the race."""
    ta = catalog.get_trace(full, REFERENCE_UID, a)
    tb = catalog.get_trace(full, REFERENCE_UID, b)
    gap = ta["time_ms"][-1] - tb["time_ms"][-1]
    assert abs(gap - (REFERENCE_LAPS[a] - REFERENCE_LAPS[b])) <= 50


def test_the_same_metre_is_the_same_place_on_two_laps(full: Paths) -> None:
    """SC-003, measured by world position rather than by where the driver braked."""
    a, b = (catalog.get_trace(full, REFERENCE_UID, n) for n in RACING_LAPS)
    offsets = sorted(
        math.dist((a["x"][i], a["z"][i]), (b["x"][i], b["z"][i]))
        for i in range(len(a["x"]) - 1)
        if None not in (a["x"][i], b["x"][i])
    )
    assert statistics.median(offsets) < 2.0
    assert offsets[int(0.95 * len(offsets))] < 5.0


def test_sector_boundaries_agree_across_laps(full: Paths) -> None:
    """Sector lines are fixed points on the circuit, so they must land in the same place."""
    laps = catalog.get_laps(full, REFERENCE_UID)
    for column in ("sector2_start_m", "sector3_start_m"):
        values = [lap[column] for lap in laps if lap[column] is not None]
        assert max(values) - min(values) < 3.0, column


def test_the_known_corner_difference_is_visible(full: Paths) -> None:
    """Found during design: at 2 300 m lap 5 is faster than lap 2, in a lower gear."""
    two = catalog.get_trace(full, REFERENCE_UID, 2)
    five = catalog.get_trace(full, REFERENCE_UID, 5)
    assert five["speed_kph"][2300] > two["speed_kph"][2300]
    assert five["gear"][2300] < two["gear"][2300]


# ---------------------------------------------------------------- feature 003 (SC-002)


def test_front_tyre_cores_reach_105_to_107_by_lap_3(full: Paths) -> None:
    from f1dc.analysis import car

    lap3 = next(r for r in car.lap_car(full, REFERENCE_UID) if r["lap_number"] == 3)
    assert 104.5 <= lap3["tyre_inner_avg_fl"] <= 107.5
    assert 104.5 <= lap3["tyre_inner_avg_fr"] <= 107.5


def test_the_front_right_runs_hotter_than_the_front_left(full: Paths) -> None:
    from f1dc.analysis import car

    for row in car.lap_car(full, REFERENCE_UID):
        if row["tyre_surface_avg_fl"] is not None:
            assert row["tyre_surface_avg_fr"] >= row["tyre_surface_avg_fl"]


def test_excursions_on_racing_laps_3_to_5(full: Paths) -> None:
    from f1dc.analysis import car

    laps = {r["lap_number"]: r for r in car.lap_car(full, REFERENCE_UID)}
    assert laps[2]["excursions"] == 0
    assert all(laps[n]["excursions"] > 0 for n in (3, 4, 5))


def test_temperature_traces_cover_the_lap(full: Paths) -> None:
    trace = catalog.get_trace(full, REFERENCE_UID, 2)
    temps = [v for v in trace["tyre_inner_fl"] if v is not None]
    assert len(temps) > 4000
    assert 90 < max(temps) < 130
