# Implementation Plan: Session Capture & Library

**Branch**: `001-session-capture-library` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-session-capture-library/spec.md`

## Summary

Capture the telemetry F1 23 broadcasts, preserve it verbatim, interpret it into sessions,
stints and laps, and present it as a browsable library with the context needed to judge
whether two lap times are comparable.

The approach is a strict four-stage pipeline with no shortcuts between stages:

```text
F1 23 ──UDP──▶ recorder (headless process, bytes only)
                     │
                     ▼
              <data>/raw/<sessionUID>.f1raw          ◀── source of truth
                     │
                     ▼
              ingest (separate, idempotent, re-runnable)
                 ├─ dispatch on (packetFormat, packetId, packetVersion)
                 ├─ discard sessionUID == 0
                 ├─ split sessions, stints, laps
                 └─ apply session-type-dependent validity
                     │
                     ▼
              <data>/derived/<session>/*.parquet  +  DuckDB views
                     │
                     ▼
              FastAPI (read-only) ──▶ React library UI
```

A separate Tkinter launcher spawns the recorder and displays its state, satisfying the
owner's choice of manual start (spec: Resolved Decisions) without putting a UI anywhere near
the capture path.

## Technical Context

**Language/Version**: Python 3.13 (backend, capture, ingest); TypeScript 5.x (frontend)

**Primary Dependencies**:
- Capture process: **standard library only** — `socket`, `struct`, `threading`, `queue`
- Launcher: **standard library only** — `tkinter`, `subprocess`
- Ingest/store: `pyarrow`, `duckdb`, `zstandard`
- API: `fastapi`, `uvicorn`
- Frontend: `react`, `vite`
- Tests: `pytest`

**Storage**: Append-only `.f1raw` logs (uncompressed while writing, zstd afterwards) as the
system of record; Parquet files as the derived store, one directory per session; DuckDB as a
read-only query layer of views over that Parquet plus a small catalog table.

**Testing**: `pytest`, with a committed curated slice of a real capture as the primary
fixture and the full 229 MB capture as an optional local end-to-end fixture.

**Target Platform**: Windows 10/11 desktop, single machine, single user, fully offline.

**Project Type**: Desktop application — background recorder process, batch ingest CLI, local
read-only web API, browser UI.

**Performance Goals**:
- Capture loss < 0.1% of frames at 60 Hz (SC-002; measured baseline 0.205% at ~108 Hz)
- Library list renders in < 2 s with 500+ sessions (SC-007)
- Recording start to "listening" in < 5 s from one action (SC-001)
- Recording state readable within 2 s of looking (SC-010)

**Constraints**:
- No parsing, database access, compression or UI work in the capture path (principle II)
- Single writer to the derived store; the API never writes
- Data directory must default outside any cloud-sync root (principle VIII)
- Raw storage budget ≤ 1.5 GB per hour of driving (SC-006; measured 1.3 GB/h at 60 Hz)

**Scale/Scope**: One driver, one machine. Design target 500+ sessions and ~2 000 hours of
retained derived data. Raw logs bounded by retention policy.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| # | Principle | Verdict | How this design satisfies it |
|---|---|---|---|
| I | Raw capture is immutable and authoritative *(NON-NEG)* | **PASS** | Recorder appends every datagram before anything interprets it. All derived data is regenerable by re-running ingest (R4, R10). Packets we cannot yet decode — Motion, MotionEx, Participants, Event detail — are preserved in full (R6). |
| II | The capture path never blocks *(NON-NEG)* | **PASS** | Recorder is its own process with no UI, no parser and no database. Receive thread does only `recv` + `queue.put`; a writer thread owns the disk. The launcher GUI is a *separate process* polling a status file (R2, R3). |
| III | Parsers selected by wire contract | **PASS** | Registry keyed on `(packetFormat, packetId, packetVersion)`. Unknown tuples are counted and reported, never coerced (R5, FR-017). |
| IV | Parsers validated against real bytes *(NON-NEG)* | **PASS** | Committed fixture slice of a real capture; every codec asserts its field sizes sum to the documented wire size at import (R5, R11). |
| V | Distance is the comparison axis | **N/A — not precluded** | This feature performs no lap comparison, so the gate does not bind. See *Deferred by design* below for why not persisting per-frame channels now is safe. |
| VI | Never present incomparable laps *(NON-NEG)* | **PASS** | Validity branches by session type (R9, FR-012). Comparability context is displayed with every lap time (FR-022). Non-counting and abandoned-session laps cannot become personal bests (FR-024). |
| VII | Ingest idempotent, re-runnable, isolated | **PASS** | Ingest is a separate process; re-ingesting rewrites one session directory atomically. `sessionUID == 0` discarded (R7, R10). |
| VIII | Data never in a cloud-sync root | **PASS** | Data directory defaults to `C:\F1Data\`; startup refuses to use a detected sync root without explicit override. |

**Result: no violations. Complexity Tracking table is intentionally empty.**

### Post-design re-check (after Phase 1)

Re-evaluated after `data-model.md`, `contracts/` and `quickstart.md` were written. Still no
violations. Three points were sharpened by the design work rather than merely restated:

- **Principle II gained a testable boundary.** `capture/` is the only package permitted zero
  third-party imports, and that is enforced by a lint rule rather than left to discipline.
- **Principle VI gained a single home.** The `counts` rule and `exclusion_reason` are
  computed once during ingest and returned by the API, so no client can re-derive validity
  differently. This is why `GET /api/sessions/{uid}/laps` returns every lap *with* its
  exclusion reason instead of returning a pre-filtered list.
- **Principle VII became structural rather than procedural.** Ingest writes to a temporary
  directory and renames it into place, so idempotence is a property of the layout, not of
  careful transaction handling.

The derived-store schema is documented in [data-model.md](./data-model.md) rather than as a
separate contract file, to avoid two documents that can drift apart.

### Deferred by design

**Per-frame telemetry channels are not persisted in this feature.** Ingest parses every
packet in order to split laps, but writes only session, stint and lap records. Feature 002
will add channel extraction and re-run ingest over retained raw logs — which is precisely the
flexibility principle I exists to buy, not a shortcut around it.

**One risk this creates, and its mitigation**: raw retention is 90 days (R14). If channel
extraction arrived after a raw log had been pruned, that session could never gain channels.
Therefore **automatic pruning ships disabled in this feature** and must be invoked manually.
Enabling it by default is deferred until features 002 and 003 have landed.

## Project Structure

### Documentation (this feature)

```text
specs/001-session-capture-library/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── raw-log-format.md    # system of record; breaking changes need a version bump
│   ├── cli.md               # operator interface + recorder status file
│   └── http-api.md          # read-only API consumed by the frontend
├── checklists/
│   └── requirements.md
└── tasks.md             # Created later by /speckit-tasks
```

### Source Code (repository root)

```text
src/f1dc/
├── config.py                    # data dir resolution, cloud-sync-root detection
├── capture/                     # STDLIB ONLY -- principle II applies here
│   ├── recorder.py              # recv thread -> bounded queue -> writer thread
│   ├── rawlog.py                # record framing (write side)
│   └── status.py                # status file the launcher polls
├── launcher/
│   └── app.py                   # Tkinter window; spawns + supervises recorder
├── wire/
│   ├── header.py                # 29-byte packet header
│   ├── registry.py              # (format, id, version) -> codec
│   └── f1_2023/
│       ├── session.py           lap_data.py          car_status.py
│       ├── car_damage.py        car_setups.py        session_history.py
│       ├── final_classification.py  tyre_sets.py     event.py
│       └── enums.py             # tracks, session types, weather, compounds
├── ingest/
│   ├── pipeline.py              # orchestration, idempotent per session
│   ├── sessionizer.py           # sessionUID boundaries, uid==0, end detection
│   ├── laps.py                  # lap splitting, sector recombination, validity
│   └── compress.py              # post-session zstd
├── store/
│   ├── layout.py                # parquet path scheme
│   ├── schema.py                # pyarrow schemas
│   └── catalog.py               # duckdb views + catalog table
├── api/
│   ├── main.py                  # FastAPI, read-only
│   └── routes/sessions.py
└── cli/
    └── main.py                  # f1dc record | ingest | serve | doctor | prune

frontend/
├── src/
│   ├── pages/                   # SessionLibrary.tsx, SessionDetail.tsx
│   ├── components/              # RecordingBanner, SessionCard, LapTable, ContextPanel
│   └── api/client.ts
├── index.html
└── vite.config.ts

tests/
├── fixtures/
│   └── calibration_slice.f1raw  # committed, < 5 MB, real bytes, all packet types
├── unit/                        # codecs, framing, lap splitting, validity rules
├── contract/                    # wire sizes, raw log format, API shapes
└── integration/                 # full raw -> parquet -> API, idempotence
```

**Structure Decision**: A single Python package (`src/f1dc/`) with a separate `frontend/`
tree. The package is subdivided by pipeline stage rather than by technical layer, so that the
constitution's boundaries are visible in the directory structure itself — `capture/` is the
only place principle II binds, and it is the only package permitted to have zero third-party
imports. A lint rule enforces that.

`frontend/` is separate because it is a different toolchain, and because the API boundary
between them is the enforcement point for "the UI never writes".

## Complexity Tracking

> No constitution violations. This table is intentionally empty.
