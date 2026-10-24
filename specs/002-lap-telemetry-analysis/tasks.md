---
description: "Task list for feature 002 — Lap Telemetry Analysis"
---

# Tasks: Lap Telemetry Analysis

**Input**: [plan.md](./plan.md) · [spec.md](./spec.md) · [research.md](./research.md) ·
[data-model.md](./data-model.md) · [contracts/http-api.md](./contracts/http-api.md)

**Status**: Implemented. 300 tests pass, plus 14 precision tests that need `--raw`; ruff clean.

**Deviations from this plan**, recorded rather than silently absorbed:

- **S1 was not delegated.** The plan expected the routes to hold logic, but it all landed
  in `analysis/compare.py`, leaving ~60 lines of thin wrapper. Briefing a cold agent would
  have cost more than writing them -- the trade-off R11 itself describes.
- **Frontend fixes went back to the same S2 agent**, which still had the code in context,
  rather than to a fresh one: lap 1 as a poor default compared lap, a fragmented map when
  the compared lap has gaps, and a pace-chart click that did not register.
- **Three trace rules were added after real data broke the first version**: closing a lap
  at the chequered-flag wrap instead of treating it as a flashback; no time interpolated
  across a leading gap; and no finish anchor unless the data reaches the line.
- **SC-003 is measured by world position**, not braking point, because braking points move
  with driving (2 218 / 2 230 / 2 216 m at one corner) rather than with alignment error.
- **Feature 001's loss metric was fixed** after it misreported 15 of the owner's 35
  sessions (see 001 data-model, *Measuring loss*). Ingest version 1.1.1.

**Tests**: mandatory (constitution principle IV).

## Format: `[ID] [P?] [Story] {model} Description`

`{model}` names the model that does the task (research R11). Tasks sharing a **batch**
label go to one sub-agent in one delegation, so the cost of briefing an agent from cold
is paid once per batch rather than once per task.

| Batch | Model | Tasks |
|---|---|---|
| **H1** | Haiku | T003–T008: codecs, codec tests, store additions |
| **S1** | Sonnet | T018–T021, T027, T030: API routes and their contract tests |
| **S2** | Sonnet | T022–T025, T028, T031, T033: frontend |
| — | Opus | everything else: the algorithmic core, fixture, verification |

---

## Phase 1: Setup

- [x] T001 {opus} Add `numpy` to `pyproject.toml` dependencies; bump `INGEST_VERSION` to `1.1.0` in `src/f1dc/ingest/__init__.py`
- [x] T002 [P] {opus} Add `uplot` to `frontend/package.json`

## Phase 2: Foundational (blocks every story)

- [x] T003 [P] {haiku · H1} Codec `src/f1dc/wire/f1_2023/car_telemetry.py`: `PerCarCodec`, packet id 6, 1352 bytes, item `<HfffBbHBBH4H4B4BH4f4B>`, trailer `<BBb>`; per-wheel fields named `_rl/_rr/_fl/_fr`
- [x] T004 [P] {haiku · H1} Codec `src/f1dc/wire/f1_2023/motion.py`: `PerCarCodec`, packet id 0, 1349 bytes, item `<3f3f3h3h3f3f>` (research R1)
- [x] T005 {haiku · H1} Register both in `wire/f1_2023/__init__.py` `CODECS`; remove ids 0 and 6 from `UNDECODED_PACKET_IDS`
- [x] T006 [P] {haiku · H1} Tests `tests/unit/test_codecs_motion.py`: decode both from the fixture; Motion speed from velocity matches CarTelemetry speed within 2 km/h on the same frame
- [x] T007 [P] {haiku · H1} `TRACE_SCHEMA` in `store/schema.py`, per data-model.md
- [x] T008 [P] {haiku · H1} `TRACES_FILE` in `store/layout.py`; `get_trace(paths, uid, lap)` in `store/catalog.py`, returning columnar lists or None
- [x] T009 {opus} Rebuild the fixture per research R10: also keep every 10th frame of packets 0/2/6 during laps 2 and 5; raise the size-budget test to 10 MB
- [x] T010 {opus} `src/f1dc/ingest/traces.py`: frame join (R2), negative-distance drop (R3), rewind guard (R4), one-metre resample with null gaps and finish anchor (R5)
- [x] T011 {opus} Wire traces into `ingest/pipeline.py` and `ingest/sessionizer.py`; write `traces.parquet`; add it to the idempotence `RESULT_FILES`
- [x] T012 {opus} Tests `tests/unit/test_traces.py`: grid spacing, step-held gear, null gaps, rewind truncation, anchor equals official lap time, negative distance dropped
- [x] T013 {opus} Re-ingest `C:\F1Data` and verify the reference race gains traces (SC-004)

**Checkpoint**: every lap has a trace, derived from existing recordings.

## Phase 3: US1 — Compare how two laps were driven (P1) 🎯 MVP

- [x] T014 {opus} `src/f1dc/analysis/compare.py`: comparability rules (R7) and the context diff (FR-014)
- [x] T015 {opus} Sector boundaries in metres (`sectors_m`) from LapData sector transitions (FR-013)
- [x] T016 {opus} Tests `tests/unit/test_compare.py`: refusals for different circuits, an incomplete reference and missing traces; context diff
- [x] T017 {opus} Default reference = best counting lap (FR-018)
- [x] T018 [P] {sonnet · S1} `GET /api/sessions/{uid}/laps/{n}/trace` per contract
- [x] T019 [P] {sonnet · S1} `GET /api/laps?track_id=` per contract
- [x] T020 {sonnet · S1} `GET /api/compare` per contract, delegating to `analysis/compare.py`
- [x] T021 {sonnet · S1} Contract tests `tests/contract/test_api_analysis.py`
- [x] T022 {sonnet · S2} `frontend/src/charts/TraceCharts.tsx`: stacked uPlot charts with a shared distance axis and synced cursor and zoom (FR-009 to FR-012), sector lines (FR-013), null gaps drawn as gaps
- [x] T023 {sonnet · S2} `frontend/src/Compare.tsx`: lap pickers across sessions at one circuit, context side by side with differences highlighted, excluded laps marked (FR-014, FR-015)
- [x] T024 {sonnet · S2} G-force traces in `TraceCharts.tsx` (FR-010)
- [x] T025 {sonnet · S2} A "Compare" entry point from `SessionDetail.tsx`

## Phase 4: US2 — Time gained or lost (P2)

- [x] T026 {opus} Running time gap in `analysis/compare.py` (R8) with tests: gap at the line equals the lap-time difference
- [x] T027 {sonnet · S1} Include `gap` in the `/api/compare` response, with contract test
- [x] T028 {sonnet · S2} `frontend/src/charts/GapChart.tsx`, synced with the traces

## Phase 5: US3 — Pace across a session (P3)

- [x] T029 {opus} `pace()` in `analysis/compare.py`: laps and stints for the chart
- [x] T030 {sonnet · S1} `GET /api/sessions/{uid}/pace`, with contract test
- [x] T031 {sonnet · S2} `frontend/src/charts/PaceChart.tsx`: stints shaded, excluded laps marked, click a lap to compare it (FR-020 to FR-023)

## Phase 6: US4 — Circuit map (P4)

- [x] T032 {opus} Verify X/Z traces close into a loop for every complete lap in the reference race
- [x] T033 {sonnet · S2} `frontend/src/charts/TrackMap.tsx`: canvas outline from X/Z, colour by speed, throttle or brake, cursor marker synced (FR-024 to FR-026)

## Phase 7: Polish & verification

- [x] T034 {opus} `tests/integration/test_trace_precision.py` (`--raw`): time gap at the line within 50 ms (SC-002); braking points within 5 m across laps (SC-003)
- [x] T035 {opus} Storage check: trace bytes per hour of driving under 50 MB (SC-007)
- [x] T036 {opus} Build the frontend; verify every view in the browser against the real race; review all delegated code
- [x] T037 {opus} README: the new views

---

## Dependencies

```text
T001-T002 ─▶ H1 (T003-T008) ─┐
             T009 ───────────┼─▶ T010-T013 ─▶ T014-T017, T026, T029 ─▶ S1 ─┐
                             │                                              ├─▶ T032-T037
                             └──────────────── S2 (needs only the contract) ┘
```

H1 runs in the background while Opus builds the fixture. S2 depends only on the API
contract, so it runs in parallel with the Opus work and with S1. Its output is checked
against the real API in T036.
