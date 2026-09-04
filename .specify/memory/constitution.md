<!--
SYNC IMPACT REPORT
Version change: none -> 1.0.0 (initial ratification)
Modified principles: none (new document)
Added sections:
  - Core Principles (I-VIII)
  - Technology Constraints
  - Development Workflow
  - Governance
Removed sections: none
Template placeholders resolved: all
Deferred TODOs: none
Templates requiring review: .specify/templates/plan-template.md,
  .specify/templates/spec-template.md, .specify/templates/tasks-template.md
  (read constitution at runtime; no edits made here)
-->

# F1 Data Center Constitution

## Core Principles

### I. Raw Capture Is Immutable and Authoritative (NON-NEGOTIABLE)

Every UDP datagram received MUST be appended to a raw log before any parsing, filtering,
or interpretation occurs. The raw log is the single source of truth and MUST be treated as
append-only. Every derived artifact — parsed tables, resampled laps, aggregates, charts —
MUST be fully reproducible from raw logs alone. No feature may depend on data that was not
first captured raw.

Rationale: F1 23 broadcasts one-way UDP with no replay and no backfill; a session not
captured is gone permanently. Parsers and schemas will change repeatedly, and raw logs make
every past session re-analysable under future code. Verified 2026-09-04: a single capture
contained all 13 packet types, including four the project cannot yet parse.

### II. The Capture Path Never Blocks (NON-NEGOTIABLE)

The recorder MUST perform only socket reads and byte appends. Parsing, database access,
compression, aggregation, and UI updates are FORBIDDEN inside the capture path. Every
session MUST record and report its own measured packet loss.

Rationale: measured baseline on 2026-09-04 was 82 lost frames (0.205%) at ~108 Hz,
including one 79-frame gap attributed to a filesystem stall. Any work added to the socket
loop increases silent, unrecoverable data loss.

### III. Parsers Are Selected by Wire Contract, Never Assumed

Every parser MUST be dispatched on the tuple (packetFormat, packetId, packetVersion) read
from the packet header. Hardcoding the 2023 format is FORBIDDEN. Unknown tuples MUST be
logged and skipped — never guessed at, never coerced into a neighbouring parser.

Rationale: keeps F1 24/25/26 support additive rather than a rewrite, and prevents a future
game patch from silently corrupting historical analysis.

### IV. Parsers Are Validated Against Real Captured Bytes (NON-NEGOTIABLE)

No parser may be accepted as correct on the basis of a specification document alone. Every
packet parser MUST carry a regression test asserting against bytes from a real capture
fixture, and its field sizes MUST sum exactly to the documented wire size.

Rationale: binary offset errors fail silently, producing plausible but wrong numbers. Two
real defects were caught this way before any code was written: sector times split across
separate millisecond and minute fields, and `m_lastLapTimeInMS` being reported against the
following lap number.

### V. Distance Is the Comparison Axis

Lap comparison MUST be performed on a fixed lap-distance grid, never on elapsed time. The
canonical derived artifact for each lap is its channel set resampled onto that grid, keyed
by (trackId, lapDistance).

Rationale: two laps of the same corner occur at different clock times but the same distance;
time-axis comparison is meaningless. At 60 Hz this grid is satisfied to better than 0.5 m
everywhere braking and cornering occur.

### VI. Never Present Incomparable Laps Side by Side (NON-NEGOTIABLE)

Any lap time displayed alongside another MUST carry its comparability context: session type,
assist settings, tyre compound and age, fuel load, weather, track temperature, and AI
difficulty. "Clean lap" MUST be defined once, MUST branch on session type, and MUST be
applied uniformly by every statistic in the system.

Rationale: assists alone change lap time fundamentally, so an unlabelled improvement may be
a settings change rather than driver progress. Measured 2026-09-04: a Race session recorded
zero invalidated laps across all 22 cars while the player accumulated two corner-cutting
warnings — race sessions penalise rather than invalidate, so a single validity rule across
session types would be silently wrong.

### VII. Ingest Is Idempotent, Re-Runnable, and Isolated

Re-running ingest over an unchanged raw log MUST produce identical derived output. Ingest
MUST NOT execute inside the capture process. Records carrying `sessionUID == 0` MUST be
discarded as menu-state noise.

Rationale: idempotence is what makes Principle I usable — reprocessing history must be
routine, not risky. Isolation keeps the single-writer storage engine free of lock contention
with the recorder.

### VIII. Data Never Lives in a Cloud-Sync Root

Raw logs and derived stores MUST default to a location outside any cloud-sync directory
(OneDrive, Dropbox, Google Drive). Source code MAY live under sync; data MAY NOT.

Rationale: raw capture runs at roughly 1.3 GB/hour at 60 Hz. Sync clients contend for open
file handles on actively-written captures and will upload every byte.

## Technology Constraints

- Capture, parsing, and ingest are Python 3.13+; the capture path uses the standard library
  only, with no third-party dependency in the socket loop.
- Storage is an append-only raw log plus a columnar derived store (Parquet with DuckDB for
  query). The derived store has exactly one writer.
- The user interface is a local web application and is READ-ONLY against the derived store.
- Recording scope is the player car at full rate. Whole-field information is sourced only
  from SessionHistory, FinalClassification, Participants, Session, and TyreSets packets.
  Full-rate telemetry for non-player cars is explicitly out of scope, and remains
  recoverable from raw logs should that decision be revisited.
- Target platform is F1 23, packet format 2023, at a 60 Hz send rate on Windows.

## Development Workflow

- Feature order is fixed: session library and progression tracking first, race and strategy
  analysis second, setup notebook third. Each builds additively on the same derived store.
- Every change touching a parser MUST run the capture-fixture regression suite before merge.
- Storage and throughput budgets are tracked explicitly and reviewed when the capture
  scope changes.
- Claims about game behaviour MUST be supported by a measurement from a real capture.
  Assumptions about the wire format, packet rates, or in-game semantics are not acceptable
  evidence in a spec, plan, or review.

## Governance

This constitution supersedes all other development practices for this project. Amendments
require a version bump, a written rationale, and a Sync Impact Report recorded in this file.
Principles marked NON-NEGOTIABLE additionally require explicit owner approval to amend or
remove.

Versioning follows semantic rules: MAJOR for backward-incompatible principle removals or
redefinitions, MINOR for a new principle or materially expanded guidance, PATCH for
clarifications and non-semantic refinements.

Compliance is verified during `/speckit-analyze` before `/speckit-implement`. Any plan or
task that violates a principle MUST either be revised or accompanied by a documented,
approved exception recorded in the relevant plan file.

**Version**: 1.0.0 | **Ratified**: 2026-09-04 | **Last Amended**: 2026-09-04
