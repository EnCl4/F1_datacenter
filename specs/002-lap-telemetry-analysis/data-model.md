# Phase 1 Data Model: Lap Telemetry Analysis

**Feature**: `002-lap-telemetry-analysis` | **Date**: 2026-10-24

Adds one derived table. Like everything derived, it is regenerable from the raw log
(principle I).

## Entity: Lap Trace — `traces.parquet`, one per session directory

One row per lap per metre of track, plus one finish-anchor row per completed lap.

| Column | Type | Notes |
|---|---|---|
| `session_uid` | string | |
| `lap_number` | int32 | |
| `distance_m` | int32 | 0 … track length. The finish anchor is exactly the track length. |
| `time_ms` | float32 | Elapsed lap time at this point. The anchor carries the official lap time. |
| `speed_kph` | float32 | CarTelemetry |
| `throttle` | float32 | 0–1 |
| `brake` | float32 | 0–1 |
| `steer` | float32 | −1 (left) … +1 (right) |
| `gear` | float32 | −1 reverse, 0 neutral, 1–8. Step-held, not interpolated. |
| `rpm` | float32 | |
| `drs` | float32 | 0/1, step-held |
| `g_lat` | float32 | Motion. Cornering force. |
| `g_lon` | float32 | Motion. Braking (−) / acceleration (+). |
| `x` | float32 | Motion world position, for the circuit map |
| `z` | float32 | Motion world position, for the circuit map |

Every channel is **null** inside a recording gap (R5); nothing is invented there.

`traces.parquet` joins the result files that idempotence is defined over (feature 001,
`RESULT_FILES`): re-ingesting must reproduce it byte for byte.

## Derivation rules

1. **Join**: per `frameIdentifier`, LapData then Motion then CarTelemetry (R2).
2. **Discard** samples with `lap_distance < 0` (R3).
3. **Rewind guard**: within a lap, a drop of more than 50 m below the furthest distance
   reached truncates everything from the new distance onward (R4).
4. **Resample** to a one-metre grid: linear for continuous channels, step-held for gear and
   DRS, null across source gaps over 25 m (R5).
5. **Anchor** completed laps at `distance_m = track_length` with the official lap time from
   feature 001's lap table (R5).

## Comparison (computed, not stored)

| Field | Notes |
|---|---|
| `lap` / `reference` | `{session_uid, lap_number}` for each |
| `distance_m[]` | Shared grid, up to the shorter of the two laps |
| `gap_ms[]` | `time_lap − time_reference`. Positive = behind. Null where either lap is null. |
| `context` | Both laps' comparability context, plus a list of fields that differ (FR-014) |

**Refused** when the two sessions' `track_id` differs, when either lap has no trace, or when
the reference lap is incomplete (R7, FR-008, FR-019).
