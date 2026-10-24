# Phase 0 Research: Lap Telemetry Analysis

**Feature**: `002-lap-telemetry-analysis` | **Date**: 2026-10-24

All decisions below were checked against the reference capture (Interlagos, 5-lap race,
229 MB) before being written down, per constitution principle IV.

---

## R1. Motion packet layout — verified

**Decision**: Decode `CarMotionData` as `<3f3f3h3h3f3f>` (60 bytes): world position xyz,
world velocity xyz, forward direction xyz (int16, normalised), right direction xyz
(int16), g-force lateral/longitudinal/vertical, yaw/pitch/roll.

**Evidence**: 29 + 60 × 22 = 1349, exactly the observed wire size. Speed derived from the
Motion velocity vector peaks at **328 km/h** on lap 2; CarTelemetry reports **328 km/h**.
Two packets, computed independently, agree, which a wrong layout could not produce. Lap 2's
X/Z path is 4,219 m (official length 4,294 m, which is plausible for a racing line that
cuts corners) and closes to within 2.7 m. G-forces span ±4.0 lateral, −4.2 / +1.6
longitudinal, which is realistic for an F1 car.

CarTelemetry (`<HfffBbHBBH4H4B4BH4f4B>`, 60 bytes, 1352 total) was already
size-verified in feature 001.

## R2. Joining packets by frame — exact

**Decision**: Join LapData, Motion and CarTelemetry on `frameIdentifier`.

**Evidence**: 39,991 of 39,992 frames carry all three, always arriving in the order LapData
(2) → Motion (0) → CarTelemetry (6). A sample is emitted when CarTelemetry arrives for a
frame whose LapData has been seen. Motion is optional: if it is missing, position and
g-force are null for that sample.

## R3. Distance and lap attribution

**Decision**: Track position is `LapData.m_lapDistance`; the lap is `m_currentLapNum`. Samples
with negative distance (before the line) are discarded (spec edge case).

## R4. Rewinds within a lap — "as finally driven"

**Decision**: Within one lap, if distance drops more than **50 m** below the furthest point
reached, drop every kept sample at or beyond the new distance, then continue. The
surviving samples are the lap as finally driven (FR-005).

**Rationale**: A flashback rewinds track position mid-lap. The owner never uses
flashbacks, so this is a guard. The cost of a missing guard would be a trace that doubles
back on itself, so silently corrupt. The 50 m threshold rides out the small backward
jitter seen when stationary in the pit box.

## R5. Resampling onto a one-metre grid

**Decision**: Grid points at every whole metre from 0 to the furthest distance reached.

- Continuous channels (speed, throttle, brake, steer, rpm, g-forces, x, z, elapsed time):
  linear interpolation.
- Discrete channels (gear, DRS): the last value at or before the grid point.
- **Gaps**: where two consecutive source samples are more than **25 m** apart, grid points
  between them are null in every channel (FR-004). At full rate, samples are ~0.9 m apart
  at top speed, so only real packet loss trips this; the reference capture's 79-frame gap
  does. At the fixture's every-10th-frame rate, spacing is ~8.4 m at 328 km/h, still well
  under the threshold.
- **Finish anchor**: for a completed lap, one final grid point is added at the track
  length, carrying the official lap time. That is what makes the running time gap at the
  line equal the lap time difference exactly (FR-017, SC-002), rather than inheriting the
  error of the last sample before the line.

Implemented with `numpy.interp`, which is deterministic, so ingest stays idempotent
(principle VII). `numpy` becomes an explicit dependency. It was already present
transitively.

## R6. Storage

**Decision**: One `traces.parquet` per session directory, alongside the feature-001 files.
Columns are float32 (distance int32), zstd-compressed.

**Estimate**: ~4,300 rows × 15 columns × 4 bytes ≈ 260 KB per lap before compression; at
roughly 50 laps an hour, under 13 MB an hour, against a budget of 50 (SC-007).

Bumping `INGEST_VERSION` to **1.1.0** makes plain `f1dc ingest` re-process every existing
recording, which is how the reference race gains traces with no re-driving (SC-004).

## R7. Which laps may be compared

**Decision**: Two laps are comparable when their sessions share a `track_id`, both laps have
traces, and the reference lap is complete.

**Rationale**: Short layouts have their own track ids (feature 001, enums), so `track_id`
equality is sufficient to mean "same geometry".

## R8. Running time gap

**Decision**: `gap(d) = time_lap(d) − time_reference(d)` over the shared grid. Positive means
the compared lap is behind at that point. Computed server-side, once, for the same reason
lap validity is: one definition, no client re-deriving it differently (principle VI).

## R9. Charting library

**Decision**: **uPlot**.

**Rationale**: About 45 KB, canvas-based, comfortable with 10k+ points per series, and it
has synced cursors and synced zoom across separate charts built in. Those are exactly
FR-011 and FR-012, so they don't need hand-building.

**Rejected**: ECharts (~1 MB, capable but heavy), Plotly (~3 MB), Recharts (SVG, which
struggles at 13 channels × 4,300 points × 2 laps). The circuit map is drawn directly on a
`<canvas>` from X/Z positions; no mapping library is needed.

## R10. Test fixture

**Decision**: Rebuild the single committed fixture to also keep **every 10th frame** of
LapData, Motion and CarTelemetry during laps 2 and 5. Expected size about 9.5 MB. The
fixture budget rises from 5 MB to **10 MB**, amending feature 001's R11.

Two full laps at full rate would be 61 MB. Precision claims (SC-002 within 50 ms, SC-003
within 5 m) are therefore tested against the full local capture with `--raw`, and the
committed fixture tests structure: alignment, gaps, rewinds, the finish anchor, and
cross-circuit refusal.

## R11. Model assignment for implementation

**Decision**: Each task in `tasks.md` names the model that does it. The owner asked for
this to reduce token consumption.

| Model | Work | Why |
|---|---|---|
| Opus | Trace extraction, rewinds, resampling, time gap; fixture; verifying results against real data | Subtle to get right, and depends on findings from feature 001 |
| Sonnet | API routes, frontend charts and pages | Most of the code by volume, against a precise contract |
| Haiku | CarTelemetry and Motion codecs and their tests; schema and layout additions | Mechanical: the byte layouts are already verified (R1) |

Sub-agents start with no context, so this saves tokens only on large, well-specified work.
Small related tasks are batched into one delegation, and every delegated result is
checked against the fixture before it is accepted.
