"""T012 -- per-metre lap traces (feature 002, research R2-R5).

Three of these rules exist because real bytes broke a first version:

* the chequered-flag wrap (lap 5 of the reference race: 4 294.1 m -> 1.2 m with the lap
  clock reset to 0) was read as a flashback and deleted the whole lap;
* time was being interpolated across lap 1's 853 m of missing data;
* a lap whose data stopped short still got a finish-line row carrying its last values.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from f1dc.ingest.traces import (
    GAP_THRESHOLD_M,
    REWIND_THRESHOLD_M,
    TraceBuilder,
    resample,
)
from f1dc.store import catalog
from tests.conftest import REFERENCE_LAPS, REFERENCE_UID

TRACK = 1000


def drive(tb: TraceBuilder, points, *, lap: int = 1, start_frame: int = 0, motion: bool = True):
    """Feed (distance, time_ms, speed, gear) points as complete frames."""
    for i, (distance, time_ms, speed, gear) in enumerate(points):
        frame = start_frame + i
        tb.on_lap_data(frame, lap, distance, time_ms, 0)
        if motion:
            tb.on_motion(frame, 0.5, -0.2, distance, -distance)
        tb.on_telemetry(frame, speed, 1.0, 0.0, 0.0, gear, 11000, 0)
    return start_frame + len(points)


def straight_lap(step: float = 2.0, length: int = TRACK, lap_time: float = 20_000.0):
    """A lap at constant speed, sampled every `step` metres, finishing at the line."""
    n = int(length / step)
    return [(i * step, lap_time * i * step / length, 180.0, 5 if i * step < length / 2 else 6)
            for i in range(n + 1)]


# ---------------------------------------------------------------- the grid


def test_grid_is_one_metre_from_zero_to_the_line() -> None:
    tb = TraceBuilder()
    drive(tb, straight_lap())
    tr = tb.build(1, TRACK, 20_000)
    assert tr["distance_m"][0] == 0
    assert np.all(np.diff(tr["distance_m"]) == 1)
    assert tr["distance_m"][-1] == TRACK


def test_gear_is_step_held_never_interpolated() -> None:
    """Interpolating a gear change would invent gear 5.5."""
    tb = TraceBuilder()
    drive(tb, straight_lap())
    gears = set(tb.build(1, TRACK, 20_000)["gear"].tolist())
    assert gears <= {5.0, 6.0}


def test_the_finish_anchor_carries_the_official_lap_time() -> None:
    """Makes the running gap at the line equal the lap-time difference exactly (SC-002)."""
    tb = TraceBuilder()
    drive(tb, straight_lap(lap_time=19_876.0))
    tr = tb.build(1, TRACK, 20_000)
    assert tr["time_ms"][-1] == 20_000


def test_time_starts_at_zero_at_the_line() -> None:
    tb = TraceBuilder()
    drive(tb, [(3.0, 50.0, 180.0, 5), *straight_lap()[2:]])
    assert tb.build(1, TRACK, 20_000)["time_ms"][0] == 0


# ---------------------------------------------------------------- gaps


def test_a_gap_is_null_in_every_channel() -> None:
    """FR-004: nothing invented across real packet loss."""
    points = [p for p in straight_lap() if not (400 < p[0] < 470)]  # a 70 m hole
    tb = TraceBuilder()
    drive(tb, points)
    tr = tb.build(1, TRACK, 20_000)
    hole = (tr["distance_m"] > 400) & (tr["distance_m"] < 470)
    for channel in ("speed_kph", "time_ms", "gear", "g_lat", "x"):
        assert np.all(np.isnan(tr[channel][hole])), channel
    assert not np.any(np.isnan(tr["speed_kph"][tr["distance_m"] < 390]))


def test_spacing_under_the_threshold_is_not_a_gap() -> None:
    """The fixture keeps every 10th frame: ~8 m apart at top speed, well under 25 m."""
    tb = TraceBuilder()
    drive(tb, straight_lap(step=GAP_THRESHOLD_M - 1))
    tr = tb.build(1, TRACK, 20_000)
    assert not np.any(np.isnan(tr["speed_kph"]))


def test_a_lap_that_starts_far_past_the_line_has_a_leading_gap() -> None:
    """Lap 1 of the reference race starts at 853 m: recording began 19 s in. Time is not
    interpolated across that either."""
    tb = TraceBuilder()
    drive(tb, [p for p in straight_lap() if p[0] >= 300])
    tr = tb.build(1, TRACK, 20_000)
    assert np.all(np.isnan(tr["time_ms"][tr["distance_m"] < 300]))
    assert np.all(np.isnan(tr["speed_kph"][tr["distance_m"] < 300]))


def test_a_lap_that_stops_short_gets_no_finish_anchor() -> None:
    tb = TraceBuilder()
    drive(tb, [p for p in straight_lap() if p[0] <= 600])
    tr = tb.build(1, TRACK, 20_000)
    assert tr["distance_m"][-1] == 600, "the trace must end where the data ends"
    assert tr["time_ms"][-1] != 20_000


def test_missing_motion_nulls_only_motion_channels() -> None:
    tb = TraceBuilder()
    drive(tb, straight_lap(), motion=False)
    tr = tb.build(1, TRACK, 20_000)
    assert np.all(np.isnan(tr["g_lat"]))
    assert np.all(np.isnan(tr["x"]))
    assert not np.any(np.isnan(tr["speed_kph"]))


# ---------------------------------------------------------------- rewinds and wraps


def test_negative_distance_before_the_line_is_dropped() -> None:
    tb = TraceBuilder()
    drive(tb, [(-15.0, 0.0, 100.0, 3), (-5.0, 0.0, 100.0, 3), *straight_lap()])
    assert tb.build(1, TRACK, 20_000)["distance_m"][0] == 0


def test_a_flashback_keeps_the_lap_as_finally_driven() -> None:
    """Drive to 600 m at 180 km/h, rewind to 300 m, finish at 150 km/h. The trace from
    300 m onward must be the second attempt, not the first."""
    tb = TraceBuilder()
    first = [p for p in straight_lap() if p[0] <= 600]
    frame = drive(tb, first)
    second = [(d, t, 150.0, g) for d, t, _s, g in straight_lap() if d >= 300]
    drive(tb, second, start_frame=frame)

    tr = tb.build(1, TRACK, 20_000)
    assert tb.rewinds(1) == 1
    assert np.all(tr["speed_kph"][(tr["distance_m"] > 310) & (tr["distance_m"] < 990)] == 150)
    assert np.all(tr["speed_kph"][tr["distance_m"] < 290] == 180)


def test_small_backward_jitter_is_not_a_rewind() -> None:
    """Stationary in the pit box, distance wobbles by centimetres."""
    tb = TraceBuilder()
    pts = straight_lap()
    jittered = pts[:100] + [(pts[99][0] - 0.3, pts[99][1], 0.0, 1)] * 5 + pts[100:]
    drive(tb, jittered)
    assert tb.rewinds(1) == 0
    assert REWIND_THRESHOLD_M > 0.3


def test_crossing_the_line_closes_the_lap_rather_than_rewinding_it() -> None:
    """The chequered-flag case: the game keeps the final lap number while distance wraps
    to ~0 and the lap clock resets. Read as a flashback, this deleted the whole lap."""
    tb = TraceBuilder()
    frame = drive(tb, straight_lap())
    drive(tb, [(1.2, 0.0, 120.0, 4), (5.0, 80.0, 125.0, 4)], start_frame=frame)

    tr = tb.build(1, TRACK, 20_000)
    assert tb.rewinds(1) == 0
    assert len(tr["distance_m"]) == TRACK + 1
    assert tr["time_ms"][-1] == 20_000


# ---------------------------------------------------------------- determinism


def test_resampling_is_deterministic() -> None:
    """Ingest must be idempotent (principle VII)."""
    rows = [(d, t, s, 1.0, 0.0, 0.0, 11000, 0.1, 0.2, d, -d, g, 0)
            for d, t, s, g in straight_lap(step=3.7)]
    a, b = resample(rows, TRACK, 20_000), resample(rows, TRACK, 20_000)
    for name in a:
        assert np.array_equal(a[name], b[name], equal_nan=True), name


# ---------------------------------------------------------------- real bytes


@pytest.mark.parametrize("lap", [2, 5])
def test_fixture_laps_are_complete_traces(ingested, lap: int) -> None:
    tr = catalog.get_trace(ingested, REFERENCE_UID, lap)
    assert tr is not None
    assert len(tr["distance_m"]) == 4295
    assert tr["distance_m"][-1] == 4294
    assert tr["time_ms"][-1] == REFERENCE_LAPS[lap]
    assert sum(v is None for v in tr["speed_kph"]) == 0


def test_the_gap_at_the_line_equals_the_lap_time_difference(ingested) -> None:
    a = catalog.get_trace(ingested, REFERENCE_UID, 5)
    b = catalog.get_trace(ingested, REFERENCE_UID, 2)
    assert a["time_ms"][-1] - b["time_ms"][-1] == REFERENCE_LAPS[5] - REFERENCE_LAPS[2]


def test_laps_without_channel_data_have_no_trace(ingested) -> None:
    """The fixture keeps channel data for laps 2 and 5 only."""
    assert catalog.get_trace(ingested, REFERENCE_UID, 3) is None


def test_values_are_physically_plausible(ingested) -> None:
    tr = catalog.get_trace(ingested, REFERENCE_UID, 2)
    speeds = [v for v in tr["speed_kph"] if v is not None]
    assert 300 < max(speeds) < 350
    assert all(-8 < g < 8 for g in tr["g_lat"] if g is not None)
    assert all(not math.isnan(v) for v in speeds)
