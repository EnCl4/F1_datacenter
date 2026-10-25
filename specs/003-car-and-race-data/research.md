# Phase 0 Research: Car and Race Data

**Feature**: `003-car-and-race-data` | **Date**: 2026-10-24

Every layout and rule here was checked against the reference capture first (principle IV).

## R1. Participants packet: verified

`<7B48s3B>` per car (58 bytes): aiControlled, driverId, networkId, teamId, myTeam,
raceNumber, nationality, name (48-byte UTF-8, NUL-padded), yourTelemetry, showOnlineNames,
platform. Preceded by `numActiveCars` (1 byte). 29 + 1 + 22 × 58 = **1306**, the observed
size. Names decode cleanly (PIASTRI, RUSSELL, STROLL, ALONSO …). The player's car 19 is
VERSTAPPEN, `aiControlled = 0`.

## R2. Event detail payloads: verified

| Code | Layout | Evidence |
|---|---|---|
| FTLP | `<Bf>` vehicle, lap time (s) | 6 of 6 match a lap in that car's SessionHistory |
| OVTK | `<BB>` overtaker, overtaken | 53 events, all indices valid; 17 involve the player |
| SPTP | `<BfBBBf>` vehicle, speed, overall-fastest, driver-fastest, fastest vehicle, fastest speed | 79–344 km/h |
| PENA | `<7B>` penalty type, infringement, vehicle, other vehicle, time, lap, places gained | The player's two entries, on laps 1 and 4, are the two corner-cutting warnings found in feature 001 |
| RTMT, RCWN | `<B>` vehicle | — |

## R3. Off-track detection

**Surface types seen**: 0 tarmac (152 133 wheel-samples), 1 rumble strip (7 174), 7 grass
(476), 10 metal (181, the pit lane). An excursion is any wheel on **3 rock, 4 gravel,
5 mud, 6 sand or 7 grass**. Kerbs (1), concrete (2) and metal (10) are not (FR-010).

**Known limit**: running wide onto *tarmac* run-off cannot be seen this way, since the
surface reads as tarmac. Corner-cutting warnings (FR-012) cover part of that gap.

An excursion is a contiguous run of off-track samples, recorded with its start distance,
length and wheels. Runs separated by under 5 m are merged, so a wheel flickering on a grass
edge counts once.

## R4. Energy counters reset at the line: verified

`ers_deployed_this_lap` just before each lap change: 2.58, 1.86, 1.74, 2.75 MJ; just after:
0.00 every time. Per-lap deployed and harvested energy are therefore **the last values
read before the lap number changes** (FR-007). On the final lap the closing value is the
last one before the chequered-flag wrap (feature 002, traces rule).

## R5. A tyre change inside a lap (FR-005)

Tyre and brake aggregates for a lap use only samples taken while tyre age equals the
lap's starting tyre age, i.e. before a mid-lap change. The lap is flagged
`tyre_change_in_lap`. On the reference race that is lap 4.

## R6. Where data lives

| File (per session) | Content |
|---|---|
| `lap_car.parquet` | one row per lap: tyres, brakes, pressures, energy, fuel, settings, damage, excursions, DRS, position, gap ahead |
| `excursions.parquet` | one row per excursion |
| `field.parquet`, `field_laps.parquet` | every car: name, team, number, best lap, finish; every lap time |
| `timeline.parquet` | weather and temperatures, a row on each change |
| `events.parquet` | overtakes, penalties, fastest laps, speed traps, retirements |
| `tyre_sets.parquet` | the player's sets with the game's lap-delta estimate |
| `traces.parquet` (extended) | + tyre surface and core temperature, brake temperature and pressure per wheel, gap ahead, off-track flag |

New files rather than wider old ones keep feature 001/002 schemas stable, and each is
directly queryable per lap and session (FR-026). `INGEST_VERSION` → **1.2.0**, so one
re-ingest adds everything to existing sessions (SC-001).

**Events → laps**: an event's lap is the player's lap at that session time.

## R7. Deleting a session safely

Order matters, because a partial deletion is worse than none: if the derived data went
first and the raw log could then not be removed, the next ingest would resurrect the
session.

1. **Checks**, refusing with a reason: the session exists; the typed name matches
   `track_name` (case-insensitive, trimmed); the session is not the one being recorded
   (from the recorder status file); the raw log holds no other ingested session.
2. **Lock**: `derived/.write.lock`, created exclusively. **Ingest takes the same lock**,
   so the two can never interleave (FR-031). A lock older than one hour is stale and may
   be taken over. Liveness is never probed with `os.kill(pid, 0)`, because on Windows that
   call **terminates** the process.
3. **Tombstone**: rename the raw log(s) to `*.deleted` (which ingest ignores) and the
   session directory to `.deleting-<uid>` (which the library ignores). If either rename
   fails, both are rolled back and nothing is deleted.
4. **Remove** the tombstoned files and the starred entry. If removal fails, the leftovers
   are invisible and non-resurrectable, and they are reported (FR-032).

The confirmation is checked by the **server** (FR-028): `DELETE` without a matching
`confirm` deletes nothing, so a stray request or a page bug cannot delete anything.

## R8. Model assignment

| Model | Work |
|---|---|
| Haiku (batch H1) | Participants codec, event-detail decoding, new schemas and layout constants, their tests |
| Sonnet (batch S1) | All frontend: car-data charts, field, timeline, events, tyre sets, G-G diagram, new traces, map excursions, delete dialog |
| Opus | Ingest aggregation, excursions, energy rules, deletion and locking, API routes, verification against real data |

The API routes stay with Opus. As in feature 002, the logic lives in `analysis/`, which
leaves thin wrappers not worth briefing a cold agent on.
