"""T010 -- per-metre lap traces (feature 002, research R2-R5).

Turns the frame-by-frame stream into one row per metre of track per lap, so two laps can
be compared corner by corner (constitution principle V). Five rules, each from a measured
property of real captures:

* **Join by frame** (R2). LapData, Motion and CarTelemetry share a ``frameIdentifier`` and
  arrive in that order -- 39 991 of 39 992 frames in the reference capture carry all three.
* **Drop negative distance** (R3). Some laps report track position as negative just before
  the start/finish line.
* **Rewind guard** (R4). A drop of more than 50 m below the furthest point reached means
  the lap was rewound (a flashback). Everything from the new position onward is
  discarded, so the trace is the lap *as finally driven*.
* **...unless the lap just finished.** After the chequered flag the game keeps the final
  lap's number while track distance wraps from the track length back to ~0 for the
  cool-down lap. The reference race does exactly this on lap 5 (4 294.1 m -> 1.2 m). Read
  as a rewind, it deleted the whole lap. The two are told apart by the lap clock: a
  wrap resets it to ~0, a flashback returns it to an earlier non-zero time. A finished
  lap is closed and accepts no further samples.
* **Gaps stay gaps** (R5). Where consecutive samples are more than 25 m apart the grid is
  null in every channel. Nothing is invented across real packet loss.
* **Finish anchor** (R5). A completed lap ends with a row at the track length carrying the
  official lap time, so the running time gap at the line equals the lap-time difference
  exactly rather than inheriting the error of the last sample before the line.

This module takes plain numbers, not codec objects, so it can be tested without packets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

REWIND_THRESHOLD_M = 50.0
GAP_THRESHOLD_M = 25.0
#: A lap clock below this, after one well above it, means the line was crossed (not a
#: rewind). Measured: the reference race's lap 5 goes from 72 645 ms to 0 ms at the line.
WRAP_CLOCK_MS = 2_000
WRAP_PREVIOUS_MS = 10_000

#: Continuous channels: linearly interpolated onto the grid.
CONTINUOUS = ("time_ms", "speed_kph", "throttle", "brake", "steer", "rpm", "g_lat", "g_lon", "x", "z")
#: Discrete channels: the last value at or before each grid point. Interpolating a gear
#: change would invent "gear 4.5".
DISCRETE = ("gear", "drs")
CHANNELS = ("time_ms", "speed_kph", "throttle", "brake", "steer", "gear", "rpm", "drs",
            "g_lat", "g_lon", "x", "z")


@dataclass
class _Frame:
    lap: int
    distance: float
    time_ms: float
    sector: int
    g_lat: float = math.nan
    g_lon: float = math.nan
    x: float = math.nan
    z: float = math.nan


@dataclass
class _LapSamples:
    rows: list[tuple[float, ...]] = field(default_factory=list)
    furthest: float = -1.0
    rewinds: int = 0
    closed: bool = False
    sector_starts: dict[int, float] = field(default_factory=dict)


class TraceBuilder:
    """Accumulates one session's samples, then resamples each lap on demand."""

    def __init__(self) -> None:
        self._frames: dict[int, _Frame] = {}
        self._laps: dict[int, _LapSamples] = {}
        self._last_sector: dict[int, int] = {}

    # ------------------------------------------------------------------ feeding

    def on_lap_data(
        self, frame: int, lap: int, distance: float, time_ms: float, sector: int
    ) -> None:
        """LapData opens a frame. Motion and CarTelemetry for the same frame follow it."""
        if lap <= 0:
            return
        # Only the newest frame can still be completed; older ones are abandoned.
        self._frames = {frame: _Frame(lap, distance, time_ms, sector)}

        if distance >= 0:
            previous = self._last_sector.get(lap)
            if previous is not None and sector > previous:
                self._laps.setdefault(lap, _LapSamples()).sector_starts.setdefault(
                    sector, distance
                )
            self._last_sector[lap] = sector

    def on_motion(self, frame: int, g_lat: float, g_lon: float, x: float, z: float) -> None:
        pending = self._frames.get(frame)
        if pending is not None:
            pending.g_lat, pending.g_lon, pending.x, pending.z = g_lat, g_lon, x, z

    def on_telemetry(
        self,
        frame: int,
        speed_kph: float,
        throttle: float,
        brake: float,
        steer: float,
        gear: float,
        rpm: float,
        drs: float,
    ) -> None:
        """CarTelemetry closes the frame and emits one sample."""
        pending = self._frames.pop(frame, None)
        if pending is None or pending.distance < 0:
            return  # no LapData for this frame, or before the line (R3)

        lap = self._laps.setdefault(pending.lap, _LapSamples())
        distance = pending.distance
        if lap.closed:
            return

        if distance < lap.furthest - REWIND_THRESHOLD_M and _is_wrap(lap, pending.time_ms):
            lap.closed = True  # crossed the line; the cool-down lap is not this lap
            return
        if distance < lap.furthest - REWIND_THRESHOLD_M:
            # Rewound: keep only what precedes the new position (R4).
            lap.rows = [row for row in lap.rows if row[0] < distance]
            lap.furthest = lap.rows[-1][0] if lap.rows else -1.0
            lap.rewinds += 1
            lap.sector_starts = {s: d for s, d in lap.sector_starts.items() if d < distance}
        elif lap.rows and distance <= lap.rows[-1][0]:
            # Stationary or tiny backward jitter (the pit box). The grid needs strictly
            # increasing distance; this sample adds nothing.
            return

        lap.rows.append((
            distance, pending.time_ms, speed_kph, throttle, brake, steer, rpm,
            pending.g_lat, pending.g_lon, pending.x, pending.z, gear, drs,
        ))
        lap.furthest = max(lap.furthest, distance)

    # ------------------------------------------------------------------ output

    def lap_numbers(self) -> list[int]:
        return sorted(n for n, lap in self._laps.items() if len(lap.rows) >= 2)

    def rewinds(self, lap_number: int) -> int:
        lap = self._laps.get(lap_number)
        return lap.rewinds if lap else 0

    def sector_starts(self, lap_number: int) -> list[float]:
        """Track distances where sectors 2 and 3 begin, for chart markers (FR-013)."""
        lap = self._laps.get(lap_number)
        if lap is None:
            return []
        return [round(lap.sector_starts[s], 1) for s in sorted(lap.sector_starts)]

    def build(
        self, lap_number: int, track_length: int, lap_time_ms: int | None
    ) -> dict[str, np.ndarray] | None:
        """Resample one lap onto the one-metre grid. None if there is nothing usable."""
        lap = self._laps.get(lap_number)
        if lap is None or len(lap.rows) < 2:
            return None
        return resample(lap.rows, track_length, lap_time_ms)


def _is_wrap(lap: _LapSamples, time_ms: float) -> bool:
    """Crossing the line resets the lap clock to ~0; a flashback does not."""
    return bool(lap.rows) and time_ms < WRAP_CLOCK_MS and lap.rows[-1][1] > WRAP_PREVIOUS_MS


def resample(
    rows: list[tuple[float, ...]], track_length: int, lap_time_ms: int | None
) -> dict[str, np.ndarray]:
    """Resample samples ``(distance, time, speed, throttle, brake, steer, rpm, g_lat, g_lon,
    x, z, gear, drs)`` onto whole metres. Deterministic, so ingest stays idempotent."""
    data = np.asarray(rows, dtype=np.float64)
    d = data[:, 0]
    source = {
        "time_ms": data[:, 1], "speed_kph": data[:, 2], "throttle": data[:, 3],
        "brake": data[:, 4], "steer": data[:, 5], "rpm": data[:, 6],
        "g_lat": data[:, 7], "g_lon": data[:, 8], "x": data[:, 9], "z": data[:, 10],
        "gear": data[:, 11], "drs": data[:, 12],
    }

    # Anchor at the line only when the data actually reaches it. A lap whose samples stop
    # far short -- recording ended, or a sparse fixture -- simply ends where its data does,
    # rather than gaining an invented final stretch that carries its last-known values.
    complete = bool(
        lap_time_ms
        and lap_time_ms > 0
        and track_length > 0
        and d[-1] >= track_length - GAP_THRESHOLD_M
    )
    end = math.floor(d[-1])
    if complete:
        end = min(end, track_length - 1)  # the anchor row supplies the track length itself
    grid = np.arange(0, end + 1, dtype=np.float64)

    out: dict[str, np.ndarray] = {}
    for name in CONTINUOUS:
        values = source[name]
        known = ~np.isnan(values)
        if known.sum() < 2:
            out[name] = np.full(grid.shape, np.nan)
            continue
        xs, ys = d[known], values[known]
        if name == "time_ms":
            # The lap clock is 0 at the line by definition: anchor the start exactly
            # instead of clamping to the first sample's time.
            if xs[0] > 0:
                xs, ys = np.concatenate(([0.0], xs)), np.concatenate(([0.0], ys))
            if complete:
                xs = np.concatenate((xs, [float(track_length)]))
                ys = np.concatenate((ys, [float(lap_time_ms)]))
        out[name] = np.interp(grid, xs, ys)

    index = np.clip(np.searchsorted(d, grid, side="right") - 1, 0, len(d) - 1)
    for name in DISCRETE:
        out[name] = source[name][index]

    # Gaps: null every channel strictly between two samples too far apart (FR-004), and
    # before the first sample when it is far past the line -- the reference race's lap 1
    # starts at 853 m because recording began 19 s into the race.
    mask = np.zeros(grid.shape, dtype=bool)
    for i in np.nonzero(np.diff(d) > GAP_THRESHOLD_M)[0]:
        mask |= (grid > d[i]) & (grid < d[i + 1])
    leading = grid < d[0] if d[0] > GAP_THRESHOLD_M else np.zeros(grid.shape, dtype=bool)
    for name in CHANNELS:
        column = out[name].astype(np.float64)
        column[mask | leading] = np.nan
        out[name] = column

    if complete:
        # Finish anchor: the official lap time at exactly the track length (R5).
        grid = np.append(grid, float(track_length))
        for name in CHANNELS:
            last = out[name][-1] if len(out[name]) else np.nan
            out[name] = np.append(out[name], float(lap_time_ms) if name == "time_ms" else last)

    out["distance_m"] = grid
    return out


def to_rows(session_uid: str, lap_number: int, trace: dict[str, np.ndarray]) -> dict[str, list]:
    """Columnar dict ready for ``table_from_rows``-style construction, float32-rounded so
    re-ingest reproduces the exact same bytes."""
    n = len(trace["distance_m"])
    columns: dict[str, list] = {
        "session_uid": [session_uid] * n,
        "lap_number": [lap_number] * n,
        "distance_m": trace["distance_m"].astype(np.int32).tolist(),
    }
    for name in CHANNELS:
        values = trace[name].astype(np.float32)
        columns[name] = [None if math.isnan(v) else float(v) for v in values.tolist()]
    return columns
