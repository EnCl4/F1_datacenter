# Implementation Plan: Lap Telemetry Analysis

**Branch**: `002-lap-telemetry-analysis` | **Date**: 2026-10-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-lap-telemetry-analysis/spec.md`

## Summary

Decode the two packet types feature 001 deliberately left raw (CarTelemetry and Motion),
join them to LapData by frame, and resample every lap onto a one-metre grid. From that
one grid come all four views: overlaid traces, the running time gap, the circuit map and
session pace. Existing recordings gain all of this by re-ingesting, with no re-driving.

```text
raw log ──▶ ingest 1.1.0
              ├─ (feature 001) sessions, stints, laps
              └─ join LapData + Motion + CarTelemetry on frameIdentifier
                   ├─ drop lap_distance < 0
                   ├─ rewind guard (as finally driven)
                   └─ resample to 1 m grid, nulls across gaps, finish anchor
                        │
                        ▼
              <session>/traces.parquet
                        │
                        ▼
           API: trace · compare (gap computed once, server side) · pace · laps
                        │
                        ▼
           uPlot charts with synced cursor and zoom, canvas circuit map
```

## Technical Context

**Language/Version**: Python 3.13; TypeScript 5.x

**Primary Dependencies**: adds `numpy` (explicit; already present transitively) and
`uplot` (frontend). Nothing is added to the capture path.

**Storage**: adds `traces.parquet` per session directory (data-model.md)

**Testing**: pytest; the committed fixture is extended per research R10; precision tests
need `--raw`

**Target Platform / Project Type**: unchanged from feature 001

**Performance Goals**: comparison opens in under 2 s (SC-001); cursor sync with no
perceptible lag (SC-005); time gap at the line within 50 ms (SC-002); braking points
aligned within 5 m (SC-003)

**Constraints**: traces add at most 50 MB per hour (SC-007; estimate under 13 MB, R6). The
recorder is untouched.

**Scale/Scope**: ~4,300 points × 15 channels per lap; two laps per comparison

## Constitution Check

*GATE: before Phase 0, and re-checked after Phase 1.*

| # | Principle | Verdict | How |
|---|---|---|---|
| I | Raw capture authoritative | **PASS** | Traces derive from raw logs only. This feature is principle I paying off: the reference race gains traces with no re-driving. |
| II | Capture path never blocks | **PASS** | The recorder is not modified. |
| III | Dispatch by wire contract | **PASS** | Both new codecs register by `(format, id, version)`. Packets 0 and 6 leave the declared-undecoded list. |
| IV | Validated against real bytes | **PASS** | Motion layout verified by an independent cross-check (speed 328 = 328, R1). The fixture is extended (R10). Precision claims are tested on the full capture. |
| V | Distance is the comparison axis | **PASS (now binding)** | Deferred in feature 001; this feature implements it. Every view shares one track-distance grid. |
| VI | Never present incomparable laps | **PASS** | Cross-circuit comparison refused (409). Both laps' context is shown side by side with differences listed. Excluded laps remain comparable but are marked. |
| VII | Ingest idempotent | **PASS** | `numpy.interp` is deterministic. `traces.parquet` joins `RESULT_FILES`, so the byte-identity test covers it. |
| VIII | Data outside sync roots | **PASS** | No new locations. |

**One amendment, outside the constitution**: feature 001's R11 fixture budget rises from
5 MB to 10 MB (R10), because a lap trace cannot be tested from 20 sampled packets.

**Result: no violations. Complexity Tracking is empty.**

### Post-design re-check

Still no violations. The design sharpened principle VI further: the time gap is computed
once on the server, for the same reason lap validity is, so no chart can derive a
different answer.

## Project Structure

```text
specs/002-lap-telemetry-analysis/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md
└── tasks.md            # /speckit-tasks

src/f1dc/
├── wire/f1_2023/
│   ├── car_telemetry.py     # NEW
│   └── motion.py            # NEW
├── ingest/
│   └── traces.py            # NEW: frame join, rewind guard, resample, anchor
├── analysis/
│   └── compare.py           # NEW: comparability rules, time gap, context diff
├── store/                   # schema, layout, catalog: trace additions
└── api/routes/analysis.py   # NEW: trace, compare, pace, laps

frontend/src/
├── charts/
│   ├── TraceCharts.tsx      # stacked, synced uPlot charts
│   ├── GapChart.tsx
│   ├── TrackMap.tsx         # canvas
│   └── PaceChart.tsx
└── Compare.tsx              # lap pickers, context diff, the four views

tests/
├── unit/        test_codecs_motion.py · test_traces.py · test_compare.py
├── contract/    test_api_analysis.py
└── integration/ test_trace_precision.py   # --raw, SC-002 / SC-003
```

**Structure decision**: `analysis/` is a new package because comparison logic belongs to
neither ingest (it's computed per request, not stored) nor the API (it must be testable
without HTTP).

## Complexity Tracking

> No constitution violations. Intentionally empty.
