---
description: "Task list for feature 003 — Car and Race Data"
---

# Tasks: Car and Race Data

**Input**: [plan.md](./plan.md) · [spec.md](./spec.md) · [research.md](./research.md) ·
[data-model.md](./data-model.md) · [contracts/http-api.md](./contracts/http-api.md)

**Tests**: mandatory (principle IV). `{model}` names who does each task (research R8);
tasks sharing a batch go to one sub-agent.

| Batch | Model | Tasks |
|---|---|---|
| **H1** | Haiku | T002–T006 |
| **S1** | Sonnet | T020–T028 (frontend, against the contract) |
| — | Opus | everything else |

## Phase 1: Setup

- [x] T001 {opus} Constitution amended to 1.1.0 (deletion), `INGEST_VERSION` → 1.2.0

## Phase 2: Foundational

- [ ] T002 [P] {haiku · H1} `wire/f1_2023/participants.py`: `PerCarCodec` id 4, 1306 B, `PREFIX = <B>`, item `<7B48s3B>`; name decoded from NUL-padded UTF-8; remove 4 from `UNDECODED_PACKET_IDS`
- [ ] T003 [P] {haiku · H1} Event detail decoding in `event.py` for FTLP, OVTK, SPTP, PENA, RTMT, RCWN (research R2)
- [ ] T004 [P] {haiku · H1} Schemas for every table in data-model.md, plus the trace additions, in `store/schema.py`; file constants in `store/layout.py`
- [ ] T005 [P] {haiku · H1} Tests: participants decode with names (car 19 = VERSTAPPEN); FTLP lap times match SessionHistory; OVTK indices < num cars
- [ ] T006 {haiku · H1} Keep the existing suite green (sessionizer undecoded-set assertion → `{13}`)
- [ ] T007 {opus} `store/lock.py`: exclusive write lock, staleness after 1 h, no `os.kill` probing; ingest takes it

## Phase 3: US1 Tyres & brakes · US2 Energy · US3 Track limits · US6 Condition (P1–P3, P6)

- [ ] T008 {opus} `ingest/car.py`: per-lap aggregation into `lap_car` (R4 energy-before-reset, R5 tyre change, settings, damage, DRS, position, gap)
- [ ] T009 {opus} Excursion detection (R3) into `excursions`
- [ ] T010 {opus} Trace channel additions in `ingest/traces.py`
- [ ] T011 {opus} Timeline, events and tyre sets
- [ ] T012 {opus} Wire everything into `pipeline.py`; extend the idempotence `RESULT_FILES`
- [ ] T013 {opus} Tests: every SC-002 figure on the reference race; tyre-change exclusion; energy reset

## Phase 4: US5 The race around you (P5)

- [ ] T014 {opus} Field tables from Participants + SessionHistory + FinalClassification; placeholder names
- [ ] T015 {opus} Tests: 20 named cars, player rank 8, fastest 1:10.900

## Phase 5: US7 Delete a session (P7)

- [ ] T016 {opus} `store/delete.py`: checks, lock, tombstone with rollback, removal, report (R7)
- [ ] T017 {opus} `DELETE` route and `f1dc delete`; update the contract test to "GET plus exactly one DELETE"
- [ ] T018 {opus} Tests: wrong or missing confirmation deletes nothing; recording session refused; shared recording refused; busy refused; re-ingest does not resurrect; partial failure reported

## Phase 6: API reads

- [ ] T019 {opus} `analysis/car.py` + `api/routes/car.py`: car, excursions, field, timeline, tyre-sets; `409 data_unavailable` for pre-1.2.0 sessions

## Phase 7: Frontend (S1)

- [ ] T020 {sonnet · S1} `CarData.tsx`: per-lap tyre/brake temperatures and pressures (per wheel), wear, energy balance, fuel, settings with changes highlighted, damage
- [ ] T021 {sonnet · S1} Excursions per lap, and on the circuit map
- [ ] T022 {sonnet · S1} `charts/GGDiagram.tsx`: both laps, cursor-synced highlight (US4)
- [ ] T023 {sonnet · S1} Combined lateral + longitudinal trace; new temperature, pressure and gap traces
- [ ] T024 {sonnet · S1} `Field.tsx`: ranked, named, player row highlighted, rank stated
- [ ] T025 {sonnet · S1} `Timeline.tsx`: conditions, events, tyre sets
- [ ] T026 {sonnet · S1} `DeleteSessionDialog.tsx`: permanent warning, session summary, starred notice, typed circuit name, error shown verbatim
- [ ] T027 {sonnet · S1} Delete entry points on library cards and the session page
- [ ] T028 {sonnet · S1} Navigation between the new views

## Phase 8: Verification

- [ ] T029 {opus} Re-ingest the owner's library; check SC-001/SC-006 (storage) on real data
- [ ] T030 {opus} Browser check of every view against real data; deletion checked on a **sandbox copy only**
- [ ] T031 {opus} Review the delegated code; README
