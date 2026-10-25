# Implementation Plan: Car and Race Data

**Branch**: `003-car-and-race-data` | **Date**: 2026-10-24 | **Spec**: [spec.md](./spec.md)

## Summary

Surface data the owner's recordings already hold: tyres, brakes, energy, fuel,
settings, damage, track limits, the named field, conditions, events and tyre sets. Add a
G-G diagram, and permanent, confirmed session deletion. Everything new is derived at
ingest into small per-session tables (data-model.md), so one re-ingest (version 1.2.0)
adds it to every existing session with no re-driving. Deletion is the single write the
amended constitution (1.1.0) allows the UI.

## Technical Context

Unchanged stack: Python 3.13, pyarrow/duckdb/numpy, FastAPI, React + uPlot. No new
dependencies. The recorder is not modified: every packet involved is already captured.
**Performance**: pages under 2 s (SC-005). **Storage**: new data at most 25 MB/hour
(SC-006).

## Constitution Check (v1.1.0)

| # | Principle | Verdict | How |
|---|---|---|---|
| I | Raw capture authoritative | **PASS** | All new data is derived from raw logs. Deletion removes whole recordings only by an explicit owner action, which the 1.1.0 clarification allows. Bytes are never modified. |
| II | Capture path never blocks | **PASS** | Recorder untouched. |
| III | Dispatch by wire contract | **PASS** | The Participants codec registers by tuple; packet 4 leaves the declared-undecoded list. |
| IV | Validated against real bytes | **PASS** | Participants (1306 B, names decode) and every event payload verified before planning (R1, R2). |
| V | Distance axis | **PASS** | New trace channels share the one-metre grid. |
| VI | No incomparable laps | **PASS** | Per-lap aggregates exclude samples after a mid-lap tyre change (R5). Excursion and energy rules are computed once, server-side. |
| VII | Ingest idempotent, isolated | **PASS** | New tables join the result set. Ingest and deletion share a write lock, so they never interleave. |
| VIII | Data outside sync roots | **PASS** | No new locations. |
| Tech | UI read-only except confirmed deletion | **PASS** | Exactly one `DELETE` route, with server-side confirmation (R7). A contract test fails on any other write route. |

**No violations. Complexity Tracking is empty.**

## Project Structure

```text
src/f1dc/
├── wire/f1_2023/participants.py   # NEW (H1)
├── wire/f1_2023/event.py          # + detail decoding (H1)
├── store/schema.py, layout.py     # + new tables (H1)
├── ingest/car.py                  # NEW: lap_car, excursions, field, timeline, events, tyre sets
├── ingest/traces.py               # + temperature, pressure, gap and off-track channels
├── ingest/pipeline.py             # writes new tables; takes the write lock
├── store/lock.py                  # NEW: write lock shared by ingest and delete
├── store/delete.py                # NEW: checks, tombstone, remove (R7)
├── analysis/car.py                # NEW: readers for the new tables
├── api/routes/car.py              # NEW: read routes + the DELETE
└── cli/main.py                    # + `f1dc delete`

frontend/src/                      # S1
├── CarData.tsx                    # per-lap tyres/brakes/energy/settings/damage/excursions
├── Field.tsx                      # named field, ranked
├── Timeline.tsx                   # conditions + events + tyre sets
├── DeleteSessionDialog.tsx        # typed-name confirmation
└── charts/GGDiagram.tsx, + traces/map additions
```

## Complexity Tracking

> No violations. Intentionally empty.
