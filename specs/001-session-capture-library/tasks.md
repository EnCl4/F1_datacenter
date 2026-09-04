---
description: "Task list for feature 001 — Session Capture & Library"
---

# Tasks: Session Capture & Library

**Input**: Design documents from `/specs/001-session-capture-library/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/)

**Status**: Implemented. 231 tests pass; `ruff` clean. Two tasks (T043, T087) remain
open because they require driving the game with the recorder running -- everything
they depend on is built and verified against the real 229 MB capture.

**Tests**: **Included and mandatory.** The template treats tests as optional, but constitution
principle IV (NON-NEGOTIABLE) requires every packet parser to be validated against real
captured bytes. Test tasks below are therefore not discretionary.

**Organization**: Grouped by user story so each can be implemented, tested and demonstrated
independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependencies
- **[Story]**: US1 / US2 / US3, mapping to the spec's user stories

## Path Conventions

Single Python package at `src/f1dc/` with a separate `frontend/` tree, per
[plan.md](./plan.md#project-structure). Tests at `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton and the guardrails that keep the constitution enforceable.

- [x] T001 Create the source tree from [plan.md](./plan.md#project-structure): `src/f1dc/{capture,launcher,wire/f1_2023,ingest,store,api/routes,cli}/`, `tests/{unit,contract,integration,fixtures}/`
- [x] T002 Add `pyproject.toml` declaring runtime deps (`pyarrow`, `duckdb`, `zstandard`, `fastapi`, `uvicorn`) and a `dev` extra (`pytest`, `ruff`)
- [x] T003 [P] Configure `ruff` formatting and linting in `pyproject.toml`
- [x] T004 [P] **Add the lint rule enforcing that `src/f1dc/capture/**` imports only the standard library** — constitution principle II made mechanical rather than remembered
- [x] T005 [P] Configure `pytest` in `pyproject.toml`, including a `needs_full_capture` marker that skips cleanly when the 229 MB capture is absent
- [x] T006 [P] Scaffold `frontend/` with Vite + React + TypeScript
- [x] T007 Implement `src/f1dc/config.py`: data-directory resolution defaulting to `C:\F1Data`, plus cloud-sync-root detection that refuses OneDrive/Dropbox/Google Drive paths without explicit override (FR-004, principle VIII)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The raw-log format and the wire codecs. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Raw log and fixture

- [x] T008 Implement `src/f1dc/capture/rawlog.py`: file header and record framing, read and write, exactly per [contracts/raw-log-format.md](./contracts/raw-log-format.md)
- [x] T009 [P] Contract test `tests/contract/test_raw_log_format.py`: round-trip, and a truncated file readable up to its last complete record
- [x] T010 **Build the committed fixture** `tests/fixtures/calibration_slice.f1raw` from `C:\F1Data\raw\calibration.bin` — under 5 MB, containing all 13 packet types, a lap transition, the pit stop, a session start and end, and the `sessionUID == 0` records (R11)

### Wire layer

- [x] T011 Implement `src/f1dc/wire/header.py`: the 29-byte packet header
- [x] T012 [P] Unit test `tests/unit/test_header.py` decoding headers from the fixture
- [x] T013 Implement `src/f1dc/wire/registry.py`: dispatch on `(packetFormat, packetId, packetVersion)`; unrecognised tuples are counted and reported, never coerced (principle III, FR-017)
- [x] T014 [P] Implement `src/f1dc/wire/f1_2023/enums.py`: track ids, session types, the `session_category` mapping, weather, tyre compounds, driver and result status
- [x] T015 [P] Implement codec `src/f1dc/wire/f1_2023/session.py` (644 bytes)
- [x] T016 [P] Implement codec `src/f1dc/wire/f1_2023/lap_data.py` (1131 bytes)
- [x] T017 [P] Implement codec `src/f1dc/wire/f1_2023/car_status.py` (1239 bytes)
- [x] T018 [P] Implement codec `src/f1dc/wire/f1_2023/car_damage.py` (953 bytes)
- [x] T019 [P] Implement codec `src/f1dc/wire/f1_2023/car_setups.py` (1107 bytes)
- [x] T020 [P] Implement codec `src/f1dc/wire/f1_2023/session_history.py` (1460 bytes)
- [x] T021 [P] Implement codec `src/f1dc/wire/f1_2023/final_classification.py` (1020 bytes)
- [x] T022 [P] Implement codec `src/f1dc/wire/f1_2023/tyre_sets.py` (231 bytes)
- [x] T023 [P] Implement codec `src/f1dc/wire/f1_2023/event.py` (45 bytes, 4-character code only — detail payload deferred per R6)
- [x] T024 Add the import-time assertion that every codec's field sizes sum to its declared wire size (principle IV)
- [x] T025 [P] Contract test `tests/contract/test_wire_sizes.py` asserting all 13 sizes against the table observed in the real capture
- [x] T026 [P] Unit test `tests/unit/test_codecs.py`: decode every packet type from the fixture and range-check values
- [x] T027 [P] Unit test `tests/unit/test_unknown_format.py`: an unrecognised tuple is reported and skipped, never decoded as a neighbour

**Checkpoint**: Raw logs can be written and read, and every packet type decodes from real bytes.

---

## Phase 3: User Story 1 — One Click Before Playing, Then Forget It (Priority: P1) 🎯 MVP

**Goal**: A single desktop action starts recording; every session in that sitting is captured
verbatim; the driver can see the state at a glance and is warned if they started late.

**Independent Test**: Start via the shortcut, drive several consecutive sessions without
touching the app, confirm one complete raw log per session with a reported loss figure.

### Tests for User Story 1

- [x] T028 [P] [US1] Integration test `tests/integration/test_recorder_lossless.py`: replay the fixture over UDP into a live recorder, assert the written log is byte-identical to what was sent
- [x] T029 [P] [US1] Unit test `tests/unit/test_status_file.py`: status file shape matches [contracts/cli.md](./contracts/cli.md), including `state` transitions
- [x] T030 [P] [US1] Unit test `tests/unit/test_loss_metric.py`: frame-gap counting, using the known 82-gap baseline from the reference capture

### Implementation for User Story 1

- [x] T031 [US1] Implement `src/f1dc/capture/recorder.py`: socket bind, `SO_RCVBUF` raised to 1 MB, receive thread performing only `recv` and `queue.put`
- [x] T032 [US1] Add the bounded queue and writer thread; record queue high-water mark as a reportable disk-pressure signal (R3)
- [x] T033 [US1] Detect `sessionUID` changes and roll to a new raw file, naming per the raw-log contract
- [x] T034 [US1] Compute the loss metric from `frameIdentifier` gaps and report it per session (FR-003)
- [x] T035 [US1] Implement `src/f1dc/capture/status.py`: JSON status file written at 2 Hz (FR-026)
- [x] T036 [US1] Implement late-start detection — first `m_currentLapNum > 1` or elevated `sessionTime` sets `started_late` (FR-027, R12)
- [x] T037 [US1] Add startup guards with the documented exit codes: port already bound → 3 (FR-006), data dir unwritable or a sync root → 4, insufficient disk → 5 (FR-005)
- [x] T038 [US1] Implement `f1dc record` in `src/f1dc/cli/main.py`
- [x] T039 [US1] Implement `src/f1dc/launcher/app.py`: Tkinter window that spawns and supervises the recorder subprocess, restarting it if it dies unexpectedly
- [x] T040 [US1] Launcher displays **Listening** / **Recording — {track}, {session type}** with current lap, readable within 2 seconds (FR-026, SC-010)
- [x] T041 [US1] Launcher surfaces the late-start warning prominently (FR-027)
- [x] T042 [US1] Add a desktop-shortcut creation step launching the window via `pythonw` with no console (FR-025)
- [ ] T043 [US1] (needs the game running) Verify [quickstart.md](./quickstart.md) Scenarios 1–4

**Checkpoint**: 🎯 **MVP.** Sessions are being captured and preserved. Nothing analyses them
yet, but no session driven from here on is ever lost.

---

## Phase 4: User Story 2 — Browse Everything I Have Driven (Priority: P2)

**Goal**: Raw logs become sessions with lap times, browsable and filterable, with incomplete
recordings visibly marked.

**Independent Test**: Run ingest over existing recordings and confirm every session is listed
with correct circuit, type, date, conditions and best lap, and can be found by filtering —
without driving anything new.

### Tests for User Story 2

- [x] T044 [P] [US2] Unit test `tests/unit/test_sessionizer.py`: `sessionUID == 0` discarded, the fixture's two sessions resolved, end classification per the data-model table
- [x] T045 [P] [US2] Unit test `tests/unit/test_lap_splitting.py`: **`m_lastLapTimeInMS` attributed to lap N−1**, and **sector recombination `minutes × 60000 + ms` not wrapping above 65.535 s** — the two defects found during design (R8)
- [x] T046 [P] [US2] Unit test `tests/unit/test_lap_validity.py`: the race branch versus the practice/qualifying branch (R9, FR-012)
- [x] T047 [P] [US2] Integration test `tests/integration/test_ingest_idempotent.py`: two runs produce byte-identical Parquet and no duplicate catalog rows (FR-015, SC-005)
- [x] T048 [P] [US2] Contract test `tests/contract/test_api_sessions.py` against [contracts/http-api.md](./contracts/http-api.md)

### Implementation for User Story 2

- [x] T049 [US2] Implement `src/f1dc/ingest/sessionizer.py`: session boundaries, `sessionUID == 0` discard, natural-end classification from `CHQF` / `SEND` / FinalClassification (FR-007, FR-014, R7)
- [x] T050 [US2] Implement `src/f1dc/ingest/laps.py`: lap splitting on `m_currentLapNum`, sector recombination, and correct lap-time attribution (FR-010)
- [x] T051 [US2] Cross-validate `LapData`-derived lap times against `SessionHistory`; disagreement fails rather than silently preferring one source (R8)
- [x] T052 [US2] Implement `src/f1dc/ingest/validity.py`: the session-type-branching `counts` rule and `exclusion_reason` (FR-012, principle VI)
- [x] T053 [P] [US2] Implement `src/f1dc/store/schema.py`: pyarrow schemas for Session, Stint and Lap per [data-model.md](./data-model.md)
- [x] T054 [P] [US2] Implement `src/f1dc/store/layout.py`: the per-session Parquet path scheme
- [x] T055 [US2] Implement `src/f1dc/ingest/pipeline.py`: write to a temp directory and rename into place, making idempotence structural (FR-015, principle VII)
- [x] T056 [US2] Implement `src/f1dc/ingest/compress.py`: zstd after session close, removing the original only after the compressed file verifies (R4)
- [x] T057 [US2] Implement `src/f1dc/store/catalog.py`: DuckDB views over the Parquet plus the recordings table
- [x] T058 [US2] Implement `f1dc ingest` with `--all` and `--force` and the documented exit codes (FR-016)
- [x] T059 [US2] Implement `src/f1dc/api/main.py`: FastAPI, read-only, bound to loopback
- [x] T060 [P] [US2] Implement `GET /api/health` and `GET /api/status`, treating a status file stale by >10 s as stopped
- [x] T061 [US2] Implement `GET /api/sessions` with circuit, category, session-type and date filters plus pagination, ordered most recent first (FR-018, FR-019, FR-020)
- [x] T062 [P] [US2] Implement `GET /api/tracks` for the filter control
- [x] T063 [US2] Build the `SessionLibrary` page in `frontend/src/pages/` — list ordered most recent first
- [x] T064 [US2] Add library filters for circuit, session category and date range
- [x] T065 [P] [US2] Build `RecordingBanner` showing when nothing is being recorded (FR-029)
- [x] T066 [US2] Mark incomplete and abandoned sessions visibly in the list (FR-023)
- [x] T067 [US2] Implement `f1dc serve` including serving the built frontend
- [x] T068 [US2] Verify [quickstart.md](./quickstart.md) Scenarios 5, 6 and 9

**Checkpoint**: Sessions are captured, interpreted and browsable. Stories 1 and 2 both stand
on their own.

---

## Phase 5: User Story 3 — Inspect One Session Lap by Lap (Priority: P3)

**Goal**: A session opens to show every lap with tyres, wear, pit involvement and whether it
counted — alongside the context that makes those times comparable.

**Independent Test**: Open the reference Interlagos race and confirm every lap matches the
game's reported times with correct tyre, validity and pit information.

### Tests for User Story 3

- [x] T069 [P] [US3] Unit test `tests/unit/test_stints.py`: stint boundaries from `SessionHistory`, cross-checked against `CarStatus` compound transitions
- [x] T070 [P] [US3] Integration test `tests/integration/test_reference_race.py`: assert the known reference figures — Interlagos, Race, 5 laps, overcast, 31 °C / 24 °C, AI 90, assists off, and laps 1:16.859 / 1:11.439 / 1:19.146 (pit) / 1:12.642
- [x] T071 [P] [US3] Contract test `tests/contract/test_api_laps.py`: every lap returned with `counts` and `exclusion_reason` present

### Implementation for User Story 3

- [x] T072 [US3] Extract stints in ingest from `SessionHistory.m_tyreStintsHistoryData`, cross-checked against `CarStatus`
- [x] T073 [US3] Enrich laps with tyre compound and age, per-wheel wear (**named `_rl`/`_rr`/`_fl`/`_fr`, never positional**), fuel, pit status, penalties and corner-cutting warnings (FR-011, FR-013)
- [x] T074 [US3] Decode per-sector validity from `m_lapValidBitFlags` onto each lap
- [x] T075 [P] [US3] Implement `GET /api/sessions/{session_uid}` returning the full comparability context (FR-022)
- [x] T076 [P] [US3] Implement `GET /api/sessions/{session_uid}/laps` returning every lap with its exclusion reason (FR-021)
- [x] T077 [P] [US3] Implement `GET /api/sessions/{session_uid}/stints`
- [x] T078 [US3] Build the `SessionDetail` page and `LapTable` component
- [x] T079 [US3] Build `ContextPanel` displaying assists, weather, temperatures and difficulty beside the lap times (FR-022, principle VI)
- [x] T080 [US3] Verify [quickstart.md](./quickstart.md) Scenarios 7 and 8

**Checkpoint**: All three user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T081 [P] Implement `f1dc doctor` per [contracts/cli.md](./contracts/cli.md), comparing observed packet sizes against expected wire sizes
- [x] T082 [P] Implement `f1dc prune` with the 90-day default — **not wired to any automatic trigger**, per [plan.md](./plan.md#deferred-by-design)
- [x] T083 [P] Implement starring a recording to exempt it from pruning (CLI only, keeping the API read-only)
- [x] T084 Validate SC-007: library lists in under 2 s with 500+ sessions, using synthesised catalog rows
- [x] T085 [P] Add structured logging across recorder, ingest and API
- [x] T086 [P] Write `README.md` including the in-game telemetry setup the driver must do once
- [ ] T087 (needs the game running) Full [quickstart.md](./quickstart.md) run-through, all 9 scenarios
- [x] T088 [P] Retire `probe_udp.py`, folding its diagnostics into `f1dc doctor`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**
- **US1 (Phase 3)**: depends on Phase 2. Independent of US2 and US3
- **US2 (Phase 4)**: depends on Phase 2. Consumes raw logs, so US1 makes it *demonstrable* on fresh data, but the committed fixture makes it fully **testable without US1**
- **US3 (Phase 5)**: depends on Phase 2 and on the US2 ingest pipeline and API shell
- **Polish (Phase 6)**: depends on the desired stories being complete

### Critical path

```text
T001 → T007 → T008 → T010 → T011 → T013 → T015..T023 → T024
                                                          ├─▶ US1 (T031..T043)  🎯 MVP
                                                          ├─▶ US2 (T049..T068)
                                                          └─▶ US3 (T072..T080, after US2)
```

**T010 (build the fixture) is the true gate.** Constitution principle IV means no codec can be
accepted without real bytes to test against, so nothing in Phase 2 completes before it.

### Within each story

- Tests are written first and must fail before implementation
- Codecs before ingest; ingest before store; store before API; API before frontend
- Story complete and independently verified before moving to the next priority

### Parallel opportunities

- T003–T006 in Phase 1
- **T015–T023: all nine codecs are independent files and parallelise cleanly** — the widest parallel block in the feature
- T025–T027 test files
- T028–T030 (US1 tests), T044–T048 (US2 tests), T069–T071 (US3 tests)
- T075–T077 API routes are independent
- Most of Phase 6

---

## Parallel Example: Phase 2 codecs

```bash
# Nine independent files, no shared state:
Task: "Implement codec src/f1dc/wire/f1_2023/session.py (644 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/lap_data.py (1131 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/car_status.py (1239 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/car_damage.py (953 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/car_setups.py (1107 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/session_history.py (1460 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/final_classification.py (1020 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/tyre_sets.py (231 bytes)"
Task: "Implement codec src/f1dc/wire/f1_2023/event.py (45 bytes)"
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 Setup
2. Phase 2 Foundational — **critical, blocks everything**
3. Phase 3 User Story 1
4. **STOP and validate**: quickstart Scenarios 1–4
5. At this point every session driven is preserved forever, even though nothing reads them yet

That ordering is deliberate. Capture is the only stage whose failure is unrecoverable, so it
ships first and alone.

### Incremental delivery

| Increment | Delivers |
|---|---|
| Setup + Foundational | Codecs proven against real bytes |
| + US1 | 🎯 Sessions preserved, never lost again |
| + US2 | Browsable library with lap times |
| + US3 | Full lap detail with comparability context |
| + Polish | Diagnostics, retention, documentation |

### Single-developer note

The template assumes a team splitting stories in parallel. Working alone, run
**P1 → P2 → P3 in order** and use the `[P]` markers only within a phase — most usefully
across the nine codecs in Phase 2.

---

## Notes

- `[P]` means different files with no shared dependency
- Test tasks here are **mandatory**, not optional — constitution principle IV
- Commit after each task or logical group
- Every checkpoint is a genuine stopping point where the feature is coherent
- The two named parsing hazards (T045) are regression tests for defects found during design,
  not hypothetical edge cases
