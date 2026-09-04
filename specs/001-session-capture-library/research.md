# Phase 0 Research: Session Capture & Library

**Feature**: `001-session-capture-library` | **Date**: 2026-09-04

All Technical Context unknowns are resolved below. Several decisions are grounded in
measurements taken from a real capture on 2026-09-04 (Interlagos, 5-lap race, 229 MB,
39 991 player telemetry frames) rather than from assumption, as required by constitution
principle IV.

---

## R1. Capture runtime

**Decision**: Python 3.13, standard library only, in a dedicated process.

**Rationale**: The measured load is ~360 packets/second at 60 Hz across all packet types.
`socket.recv` plus a file append is nowhere near Python's limits at that rate. The standard
library gives us `socket`, `struct` and `threading` with zero install surface, which matters
because the capture process is the one component whose failure loses data permanently.

**Alternatives considered**: A compiled recorder (Rust/Go/C#) would be more robust in
principle, but introduces a second toolchain for a component that is ~150 lines. Rejected as
unjustified complexity; revisit only if measured loss exceeds SC-002.

---

## R2. Recorder and user interface are separate processes

**Decision**: Two processes. A small launcher window (Tkinter, standard library) spawns a
headless recorder subprocess. The recorder writes a status file; the launcher polls it at
2 Hz and displays state.

**Rationale**: Constitution principle II forbids UI work in the capture path. Running the
GUI in the same process — even on another thread — leaves the socket loop exposed to GIL
stalls during redraws. Separate processes make compliance unambiguous rather than
argued, and leave the recorder headless and trivially testable.

This also satisfies FR-025 (a desktop shortcut launches the window, no command line) and
FR-026 (state visible at all times) without compromising principle II.

**Alternatives considered**: single process with socket thread, writer thread and GUI
thread. Cheaper, but makes principle II a judgement call. Rejected — the measured 79-frame
gap in the calibration capture is exactly the class of stall this avoids.

---

## R3. Internal capture pipeline

**Decision**: Receive thread → bounded in-memory queue → writer thread. The receive thread
performs only `recv` and `queue.put`. `SO_RCVBUF` is raised to 1 MB. Queue depth is
monitored and reported as part of the session's loss metric.

**Rationale**: Disk writes must never stall the socket. A bounded queue makes backpressure
visible rather than silent — if it ever fills, that is reportable data loss (FR-003), not a
mystery.

---

## R4. Raw log format and compression

**Decision**: The recorder writes **uncompressed** length-prefixed records
(`uint32 length`, `float64 receive timestamp`, then the datagram verbatim) to a `.f1raw`
file. Compression to `.f1raw.zst` happens **after** the session closes, in the ingest
process, using `zstandard`.

**Rationale**: Compression in the capture path is forbidden by principle II, and `zstandard`
is a third-party dependency that has no business in the recorder. Writing raw and
compressing afterwards keeps the capture path to `write()` and nothing else. The transient
uncompressed cost (~1.3 GB/hour measured at 60 Hz) is acceptable; zstd reduces it
substantially given the heavy redundancy (21 largely idle car slots per packet, and
`SessionHistory` re-sending cumulative state 20×/second).

The per-record receive timestamp makes the log replayable with original timing, which is
what allows ingest to be re-run offline (FR-016).

**Alternatives considered**: stdlib `gzip` in the capture path — still work in the socket
process, and worse ratios. Rejected.

---

## R5. Parser dispatch

**Decision**: A registry mapping `(packetFormat, packetId, packetVersion)` → codec. The
2023 codecs live under `wire/f1_2023/`. An unrecognised tuple is counted and logged, never
coerced into a neighbouring parser.

**Rationale**: Constitution principle III, and FR-017. This is what makes F1 24/25/26
support additive rather than a rewrite.

**Validated**: all 13 packet types observed in the calibration capture arrived at exactly
one size each, and every size matches the published 2023 specification:

| ID | Packet | Bytes | ID | Packet | Bytes |
|---:|---|---:|---:|---|---:|
| 0 | Motion | 1349 | 8 | FinalClassification | 1020 |
| 1 | Session | 644 | 10 | CarDamage | 953 |
| 2 | LapData | 1131 | 11 | SessionHistory | 1460 |
| 3 | Event | 45 | 12 | TyreSets | 231 |
| 4 | Participants | 1306 | 13 | MotionEx | 217 |
| 5 | CarSetups | 1107 | | | |
| 6 | CarTelemetry | 1352 | | | |
| 7 | CarStatus | 1239 | | | |

Every codec's field sizes must sum to its wire size; this is asserted at import time.

---

## R6. Packet structures not yet required

**Decision**: Motion (0), MotionEx (13), Participants (4), and the 12-byte detail payload of
Event (3) are **not** decoded in this feature. Event packets are decoded to their 4-character
code only, which is all that session-end detection requires.

**Rationale**: none of them serve a requirement in this feature — Motion and MotionEx are for
the racing-line map (deferred), Participants for rival names (deferred). Constitution
principle I means their bytes are preserved in full regardless, so a later feature can decode
them from existing recordings without re-driving anything. This is the raw-log architecture
paying off rather than a gap.

**Validated**: the 4-character event codes parse correctly today. The calibration capture
yielded `BUTN OVTK PENA FTLP TMPT SPTP DRSE RCWN CHQF SEND`.

---

## R7. Session boundaries

**Decision**: A session is identified by `sessionUID`. Records with `sessionUID == 0` are
discarded entirely. A session is considered to have ended naturally if a `SEND` (session
ended) or `CHQF` (chequered flag) event, or a FinalClassification packet, was observed;
otherwise it is marked abandoned or interrupted.

**Rationale**: FR-007, FR-014. **Validated**: the calibration capture contained two
`sessionUID` values — the real race, and a second with `uid == 0` carrying 14 Event packets
and nothing else. That is menu state, and without this rule it would appear in the library as
a phantom session.

---

## R8. Lap splitting and time fields

**Decision**: Laps are cut on `m_currentLapNum` transitions in LapData. Three specific
hazards are handled explicitly:

1. **`m_lastLapTimeInMS` is reported against the *following* lap.** The value seen during
   lap N is lap N−1's time. Lap N's own time is read after the transition to N+1, or from
   SessionHistory.
2. **Sector times are split across two fields.** `m_sectorNTimeInMS` is a `uint16` and
   saturates at 65.535 s; `m_sectorNTimeMinutes` carries the overflow. True sector time is
   `minutes × 60000 + milliseconds`. Using the millisecond field alone silently wraps on slow
   sectors — safety car, damage, Monaco.
3. **Wheel arrays are ordered rear-left, rear-right, front-left, front-right.** Not
   front-first. Applies to every tyre and brake array.

**Rationale**: FR-010, and constitution principle IV. Hazards 1 and 2 are real defects that
were caught during design against captured bytes — hazard 1 produced a plausible but wrong
lap table on the first analysis pass.

**Cross-check**: SessionHistory carries authoritative per-lap times and per-sector validity
for every car and is used to verify lap times derived from LapData. Disagreement is a test
failure, not a silent preference.

---

## R9. Lap validity branches by session type

**Decision**: Two rules.

- **Practice / Qualifying / Time Trial**: a lap counts unless `m_currentLapInvalid` is set,
  or `SessionHistory.m_lapValidBitFlags` bit 0 is clear.
- **Race**: invalidation is not the game's mechanism. A lap is excluded from pace statistics
  if it is an in-lap, out-lap, run under pit conditions, run behind a safety car, or the
  first lap of the race.

**Rationale**: FR-012, constitution principle VI. **Validated**: the calibration race
recorded **zero** invalidated laps across all 22 cars while the player accumulated two
corner-cutting warnings and a `PENA` event. A single validity rule would have classified
every race lap as clean, including the ones with track-limits infringements — and would have
silently produced false personal bests.

---

## R10. Storage layout

**Decision**: Parquet files on disk are the derived store, laid out one directory per
session. DuckDB is a **query layer with views over those Parquet files**, plus one small
catalog table; it never holds the only copy of anything.

**Rationale**: Makes FR-015 (idempotence) fall out structurally rather than requiring
transactional care — re-ingesting a session rewrites that session's directory atomically and
nothing else is touched. Rebuilding the entire derived store is `rm -rf` plus a re-run. It
also keeps DuckDB's single-writer constraint irrelevant, because ingest writes files and the
API only reads.

**Alternatives considered**: DuckDB as the system of record. Rejected — a corrupted or
schema-migrated database becomes a migration problem, whereas Parquet-per-session is
regenerable from raw at any time.

---

## R11. Test fixture strategy

**Decision**: Two tiers.

- **Committed**: a small curated slice of the calibration capture (target < 5 MB) containing
  every packet type, a lap transition, a pit stop, a session start and a session end.
  Lives in `tests/fixtures/` and is committed to the repository.
- **Local, not committed**: the full 229 MB calibration capture at
  `C:\F1Data\raw\calibration.bin`, used by slower end-to-end tests that skip cleanly when it
  is absent.

**Rationale**: Constitution principle IV requires every parser to be tested against real
bytes, but principle VIII and ordinary sense forbid committing 229 MB. A curated slice
satisfies both: real bytes, in version control, running on every change.

---

## R12. Late-start detection

**Decision**: When the first LapData for a new session arrives with `m_currentLapNum > 1`,
or the first header `sessionTime` exceeds a small threshold, the session is flagged
`started_late` and the launcher shows a warning.

**Rationale**: FR-027. Because the owner chose manual start, this is the difference between
a partial session that announces itself and one that quietly looks complete.

---

## R13. User interface stack

**Decision**: FastAPI (read-only) behind a React + TypeScript + Vite frontend.

**Rationale**: The library in this feature is a list and a detail view, which server-rendered
HTML would serve adequately. But features 002 and 003 need linked, interactive charts over
tens of thousands of points, and rewriting the shell at that point is waste. Node 22 is
already present on the machine. The API is read-only, which keeps the write path exclusively
in ingest.

**Alternatives considered**: server-rendered templates for this feature. Rejected as a known
future rewrite. A desktop-native UI (Tkinter beyond the launcher, or Qt) was rejected for the
same charting reason.

---

## R14. Retention

**Decision**: Compressed raw logs are retained 90 days. Derived Parquet and catalog entries
are retained indefinitely. A session may be starred to retain its raw log permanently.
Nothing is ever deleted without the retention policy being explicitly applied.

**Rationale**: Bounds storage growth while preserving the ability to re-interpret recent
history under improved parsers, which is the whole point of principle I. Derived data is
small enough that indefinite retention is free.
