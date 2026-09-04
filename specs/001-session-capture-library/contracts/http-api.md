# Contract: HTTP API

**Read-only.** There are no `POST`, `PUT`, `PATCH` or `DELETE` routes in this feature, and
that is a design property rather than an omission: the write path belongs exclusively to
ingest, which keeps the derived store single-writer (plan: Constitution Check VII).

Marking a session as starred is therefore a CLI action in this feature, not an API one.

Base path `/api`. Bound to `127.0.0.1` by default. No authentication — the service is local
and single-user.

---

### `GET /api/health`

```json
{ "status": "ok", "ingest_version": "1.0.0", "sessions": 47 }
```

---

### `GET /api/status`

Recorder state, read from the status file the recorder writes. Backs the library banner
required by **FR-029**, so the driver is never misled into thinking a session is being
captured when nothing is.

```json
{ "recording": false, "state": "stopped", "since": null, "session": null }
```

When active, `session` carries the same shape as the recorder status file
(see [cli.md](./cli.md)).

If the status file is absent or stale by more than 10 seconds, `state` is reported as
`stopped` — a crashed recorder must never appear to be running.

---

### `GET /api/sessions`

The library list (FR-018, FR-019, FR-020).

| Query param | Type | Notes |
|---|---|---|
| `track_id` | int | Filter by circuit |
| `session_category` | string | `practice` \| `qualifying` \| `race` \| `time_trial` |
| `session_type` | int | Finer-grained than category |
| `from` / `to` | ISO date | Date range on `started_at` |
| `include_abandoned` | bool | Default `true`; abandoned sessions are shown but marked |
| `limit` / `offset` | int | Default 50 / 0 |

Ordered by `started_at` descending — most recent first, per FR-018.

```json
{
  "total": 47,
  "items": [
    {
      "session_uid": "15975277775803518192",
      "started_at": "2026-09-04T11:04:12Z",
      "track_name": "Interlagos",
      "session_type_name": "Race",
      "session_category": "race",
      "duration_s": 371.5,
      "num_laps": 5,
      "num_counting_laps": 3,
      "best_lap_ms": 71439,
      "weather_name": "overcast",
      "air_temp_c": 24,
      "track_temp_c": 31,
      "ai_difficulty": 90,
      "assists_summary": "no assists, manual gearbox",
      "ended_naturally": true,
      "end_reason": "chequered",
      "started_late": false,
      "loss_pct": 0.205,
      "incomplete": false
    }
  ]
}
```

`best_lap_ms` is computed over **counting laps only** (FR-024). `incomplete` is true when
`loss_pct` exceeds the threshold or the session did not end naturally, and drives the
visible marking required by FR-023.

---

### `GET /api/sessions/{session_uid}`

Full session detail including the complete comparability context required by **FR-022** —
every assist individually, not just the summary string.

```json
{
  "session_uid": "15975277775803518192",
  "track_name": "Interlagos",
  "track_length_m": 4294,
  "session_type_name": "Race",
  "session_category": "race",
  "total_laps": 5,
  "conditions": { "weather_name": "overcast", "air_temp_c": 24, "track_temp_c": 31 },
  "assists": {
    "steering": 0, "braking": 0, "gearbox": 1, "pit": 0,
    "pit_release": 0, "ers": 0, "drs": 0,
    "racing_line": 0, "racing_line_type": 0
  },
  "ai_difficulty": 90,
  "recording": {
    "loss_pct": 0.205, "packets_received": 182451,
    "unknown_packets": 0, "captured_at": "2026-09-04T11:04:12Z"
  }
}
```

`404` if the session does not exist.

---

### `GET /api/sessions/{session_uid}/laps`

Backs the lap table (FR-021). Ordered by `lap_number`.

```json
{
  "items": [
    {
      "lap_number": 2,
      "lap_time_ms": 71439,
      "sector1_ms": 17204, "sector2_ms": 30118, "sector3_ms": 24117,
      "valid": true,
      "counts": true,
      "exclusion_reason": null,
      "stint_index": 0,
      "tyre_visual_compound_name": "Medium",
      "tyre_age_laps": 2,
      "is_in_lap": false, "is_out_lap": false, "pit_status": 0,
      "tyre_wear_rl": 4.1, "tyre_wear_rr": 4.4,
      "tyre_wear_fl": 3.8, "tyre_wear_fr": 3.9,
      "corner_cutting_warnings": 0,
      "penalties_s": 0
    }
  ]
}
```

Every lap is returned, including those that do not count. **`counts` and
`exclusion_reason` are always present** so the client never has to re-derive the validity
rule — that rule lives in exactly one place (principle VI).

Tyre wear fields are named per wheel rather than positional, so the rear-left-first ordering
of the source packets cannot be silently mis-mapped.

---

### `GET /api/sessions/{session_uid}/stints`

```json
{
  "items": [
    { "stint_index": 0, "start_lap": 1, "end_lap": 3,
      "tyre_visual_compound_name": "Medium", "tyre_age_start_laps": 0, "num_laps": 3 }
  ]
}
```

---

### `GET /api/tracks`

Distinct circuits present in the library, for populating the filter (FR-020).

```json
{ "items": [ { "track_id": 16, "track_name": "Interlagos", "session_count": 12 } ] }
```

---

## Error shape

```json
{ "error": { "code": "session_not_found", "message": "No session with uid 123" } }
```

`400` invalid query parameters · `404` unknown resource · `503` derived store unavailable
(never yet ingested).
