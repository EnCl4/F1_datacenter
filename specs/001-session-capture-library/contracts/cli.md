# Contract: Command Line Interface

`f1dc` is the operator interface. The driver is never *required* to use it — FR-025 demands a
desktop shortcut and no command line for normal use — but every action the app performs must
be reachable from here, for testing and recovery.

## `f1dc record`

Runs the headless recorder. This is what the launcher spawns.

```text
f1dc record [--port 20777] [--data-dir PATH] [--status-file PATH]
```

| Exit | Meaning |
|---:|---|
| 0 | Stopped cleanly by signal |
| 3 | Port already in use — another recorder or a dashboard app (FR-006) |
| 4 | Data directory unwritable, or refuses to run because it is a cloud-sync root |
| 5 | Insufficient free disk space to start (FR-005) |

Writes a JSON status file, updated at 2 Hz, which the launcher polls (FR-026):

```json
{
  "state": "listening | recording | stopped | error",
  "since": "2026-09-04T11:04:12Z",
  "session": {
    "uid": "15975277775803518192",
    "track": "Interlagos",
    "session_type": "Race",
    "current_lap": 3,
    "started_late": false
  },
  "packets": 182451,
  "bytes": 231666957,
  "loss_pct": 0.205,
  "queue_high_water": 0,
  "free_disk_gb": 412.6,
  "message": null
}
```

`state` is `listening` when no session is active and `recording` once real session traffic is
arriving. `session` is null while listening.

## `f1dc ingest`

```text
f1dc ingest [PATH ...] [--all] [--force] [--data-dir PATH]
```

Interprets raw logs into the derived store. With no arguments, ingests every raw log not yet
ingested by the current ingest version.

**Idempotent** (FR-015): re-running over the same raw log rewrites that session's directory
with identical content and creates no duplicate catalog entries. `--force` re-ingests even if
already current, which is how a parser improvement is rolled out across history (FR-016).

| Exit | Meaning |
|---:|---|
| 0 | Success |
| 6 | One or more logs contained an unrecognised packet format (FR-017); others still ingested |
| 7 | No raw logs found |

## `f1dc serve`

```text
f1dc serve [--host 127.0.0.1] [--port 8420] [--open]
```

Starts the read-only API and serves the built frontend. Binds loopback only by default.

## `f1dc doctor`

Diagnoses setup without requiring the game to be running. This is the command that answers
"why isn't it recording?".

```text
f1dc doctor [--listen-seconds 10]
```

Checks, in order: data directory writable and not a sync root; free disk space; UDP port
bindable; and, if a game is running, whether packets arrive and at what rate and sizes, with
observed packet sizes compared against the expected 2023 wire sizes.

## `f1dc prune`

```text
f1dc prune [--older-than 90d] [--dry-run] [--yes]
```

Deletes raw logs past the retention window. Never deletes starred recordings and never
deletes derived data.

**Ships disabled from automatic execution in this feature** — it must be run deliberately.
Rationale in [plan.md](../plan.md#deferred-by-design): per-frame channels are not yet
persisted, so a pruned raw log could not later gain them.
