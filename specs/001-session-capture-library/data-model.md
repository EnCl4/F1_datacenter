# Phase 1 Data Model: Session Capture & Library

**Feature**: `001-session-capture-library` | **Date**: 2026-09-04

Derived entities are stored as Parquet, one directory per session. DuckDB exposes them as
views. Nothing here is the system of record — every table is regenerable from the raw log
(constitution principle I).

**Wheel array ordering is rear-left, rear-right, front-left, front-right** in every packet
that carries one. Column names below are explicit (`_rl`, `_rr`, `_fl`, `_fr`) precisely so
this cannot be silently mis-ordered.

---

## Entity: Recording

One captured raw log. The permanent record.

| Field | Type | Notes |
|---|---|---|
| `recording_id` | string | Stable id derived from `session_uid` + capture start |
| `path` | string | Absolute path to `.f1raw` / `.f1raw.zst` |
| `captured_at` | timestamp | UTC, wall-clock at first datagram |
| `size_bytes` | int64 | On-disk size |
| `packets_received` | int64 | Datagrams written |
| `frames_lost` | int64 | From `frameIdentifier` gaps (FR-003) |
| `loss_pct` | double | `frames_lost / frames_expected × 100` |
| `queue_high_water` | int32 | Peak writer-queue depth; non-zero means disk pressure |
| `packet_format` | int32 | 2023 |
| `game_version` | string | From header major/minor |
| `unknown_packets` | int64 | Unrecognised `(format, id, version)` tuples (FR-017) |
| `compressed` | bool | zstd applied after session close |
| `starred` | bool | Exempt from retention pruning |
| `ingest_version` | string | Which ingest produced the current derived data |
| `ingested_at` | timestamp | Null if never ingested |

**Lifecycle**: `capturing → closed → compressed → ingested`. Re-ingestion moves it back
through `ingested` without touching the raw file.

---

## Entity: Session

| Field | Type | Notes |
|---|---|---|
| `session_uid` | uint64 | Primary key. **`0` is never persisted** (FR-007) |
| `recording_id` | string | FK → Recording |
| `started_at` / `ended_at` | timestamp | UTC |
| `duration_s` | double | |
| `track_id` | int8 | Raw game id |
| `track_name` | string | Resolved label |
| `track_length_m` | int32 | As reported by the game |
| `session_type` | int8 | Raw game id |
| `session_type_name` | string | `P1`…`Q3`, `Race`, `Time Trial`, … |
| `session_category` | string | **`practice` \| `qualifying` \| `race` \| `time_trial`** — drives the validity rule (R9) |
| `total_laps` | int16 | Scheduled, 0 for timed sessions |
| `weather` | int8 + `weather_name` string | |
| `air_temp_c` / `track_temp_c` | int8 | |
| `ai_difficulty` | int16 | 0–110 |
| `formula` / `game_mode` / `rule_set` | int8 | |
| `network_game` | bool | |
| `player_car_index` | int8 | Which of the 22 slots is the driver |
| `ended_naturally` | bool | FR-014 |
| `end_reason` | string | `chequered` \| `session_end` \| `abandoned` \| `interrupted` |
| `started_late` | bool | Recorder started mid-session (FR-027, R12) |
| `num_laps` / `num_counting_laps` | int16 | |
| `best_lap_ms` | int32 | **Counting laps only** (FR-024) |
| `best_lap_number` | int16 | |
| `loss_pct` | double | Denormalised from Recording for library display (FR-023) |
| `ingest_version` | string | |

### Assist configuration (embedded in Session)

`assist_steering`, `assist_braking`, `assist_gearbox`, `assist_pit`, `assist_pit_release`,
`assist_ers`, `assist_drs`, `assist_racing_line`, `assist_racing_line_type` — all `int8`,
plus a derived `assists_summary` string for display.

These are **not optional metadata**. Constitution principle VI makes them part of every lap
time's comparability context, because they change achievable lap times outright.

---

## Entity: Stint

A continuous run on one set of tyres.

| Field | Type | Notes |
|---|---|---|
| `session_uid` | uint64 | PK part 1 |
| `stint_index` | int16 | PK part 2, 0-based |
| `start_lap` / `end_lap` | int16 | `end_lap` null while current |
| `tyre_actual_compound` | int8 + name | Specific compound (C1–C5, inter, wet) |
| `tyre_visual_compound` | int8 + name | Soft / medium / hard as shown |
| `tyre_age_start_laps` | int16 | Age when fitted |
| `num_laps` | int16 | |

Sourced primarily from `SessionHistory.m_tyreStintsHistoryData`, cross-checked against
`CarStatus` compound transitions.

---

## Entity: Lap

| Field | Type | Notes |
|---|---|---|
| `session_uid` | uint64 | PK part 1 |
| `lap_number` | int16 | PK part 2 |
| `stint_index` | int16 | FK → Stint |
| `lap_time_ms` | int32 | Null if incomplete |
| `sector1_ms` / `sector2_ms` / `sector3_ms` | int32 | **Recombined**, see below |
| `valid` | bool | The game's own validity flag |
| `sector1_valid` / `sector2_valid` / `sector3_valid` | bool | From `m_lapValidBitFlags` |
| `counts` | bool | **Our rule** — branches on `session_category` (R9) |
| `exclusion_reason` | string | Null when counting. Else `invalidated` \| `in_lap` \| `out_lap` \| `pit` \| `safety_car` \| `first_lap` \| `incomplete` |
| `is_in_lap` / `is_out_lap` | bool | |
| `pit_status` | int8 | 0 none, 1 pitting, 2 in pit area |
| `num_pit_stops` | int16 | Cumulative |
| `tyre_actual_compound` / `tyre_visual_compound` | int8 + name | |
| `tyre_age_laps` | int16 | |
| `fuel_in_tank_start` | float | Kg at lap start |
| `fuel_remaining_laps` | float | Game's own estimate |
| `tyre_wear_rl/_rr/_fl/_fr` | float | Percent at lap end |
| `car_position` | int8 | |
| `penalties_s` | int8 | Accumulated |
| `corner_cutting_warnings` | int8 | |

---

## Derivation rules

These are the rules most likely to be got wrong, so they are stated once here and tested
directly (constitution principle IV).

### Sector time recombination

```text
sector_ms = m_sectorNTimeMinutes × 60000 + m_sectorNTimeInMS
```

`m_sectorNTimeInMS` is a `uint16` and saturates at 65 535 ms. Reading it alone silently
wraps any sector longer than 65.5 s — safety car, damage, or a slow circuit (R8).

### Lap time attribution

`m_lastLapTimeInMS` observed during lap *N* is the time for lap ***N − 1***. Lap *N*'s own
time is taken after the transition to *N + 1*, or from `SessionHistory`. This off-by-one
produced a wrong lap table on the first analysis pass during design and is now a named test
case (R8).

### Cross-validation

Lap times derived from `LapData` transitions **must** equal those in
`SessionHistory.m_lapHistoryData`. Disagreement is a test failure, never a silent
preference for one source.

Additionally `lap_time_ms ≈ sector1 + sector2 + sector3` (tolerance 2 ms for rounding); a
mismatch sets a data-quality flag on the lap rather than being discarded.

### `counts` — the validity rule that branches

```text
if session_category in (practice, qualifying, time_trial):
    counts = valid AND lap_time_ms is not null
else:  # race
    counts = lap_time_ms is not null
            AND NOT is_in_lap AND NOT is_out_lap
            AND pit_status == 0
            AND NOT under_safety_car
            AND lap_number > 1
```

**Why this branches**: the calibration race recorded zero invalidated laps across all 22 cars
while the player took two corner-cutting warnings. Races penalise; they do not invalidate. A
single rule would mark every race lap clean, including cut corners, and manufacture false
personal bests (R9, FR-012, principle VI).

### Session end classification

| Observed | `end_reason` | `ended_naturally` |
|---|---|---|
| `CHQF` event or FinalClassification packet | `chequered` | true |
| `SEND` event without chequered | `session_end` | true |
| Stream stops, no end event, laps present | `abandoned` | false |
| Stream stops mid-lap, recorder still running | `interrupted` | false |

---

## Storage layout

```text
<data_root>/                        # default C:\F1Data, never a cloud-sync root
├── raw/
│   └── 2026-09-04T11-04_15975277775803518192.f1raw.zst
└── derived/
    ├── catalog.duckdb              # views + recordings table; regenerable
    └── sessions/
        └── 15975277775803518192/
            ├── session.parquet
            ├── stints.parquet
            └── laps.parquet
```

Re-ingesting a session writes to a temporary directory and renames it into place, so a
failed run never leaves a half-written session and a repeated run is a no-op producing
identical bytes (FR-015, principle VII).
