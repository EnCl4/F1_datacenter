# Contract: HTTP API additions

Extends feature 001's read-only API. **Still no write routes.**

Arrays are **columnar** (one array per channel) because each lap is ~4,300 points × 15
channels. Columnar JSON is roughly a third the size of an array of objects, and it is the
shape uPlot consumes directly. Nulls mark recording gaps.

---

### `GET /api/sessions/{session_uid}/laps/{lap_number}/trace`

```json
{
  "session_uid": "15975277775803518192",
  "lap_number": 2,
  "track_id": 16,
  "track_length_m": 4294,
  "lap_time_ms": 71439,
  "counts": true,
  "exclusion_reason": null,
  "sectors_m": [1180, 2950],
  "channels": {
    "distance_m": [0, 1, 2],
    "time_ms":    [0.0, 11.2, 22.3],
    "speed_kph":  [291.0, 291.4, 291.8],
    "throttle":   [1.0, 1.0, 1.0],
    "brake":      [0.0, 0.0, 0.0],
    "steer":      [0.01, 0.01, 0.0],
    "gear":       [7, 7, 7],
    "rpm":        [11600, 11620, 11640],
    "drs":        [0, 0, 0],
    "g_lat":      [0.1, 0.1, 0.1],
    "g_lon":      [0.3, 0.3, 0.3],
    "x":          [12.5, 12.4, 12.3],
    "z":          [-80.1, -79.2, -78.3]
  }
}
```

`sectors_m` holds the track distances where sectors 2 and 3 begin, taken from where the
LapData `sector` field changes (FR-013).

| Status | When |
|---|---|
| 404 `session_not_found` / `lap_not_found` | No such session or lap |
| 409 `trace_unavailable` | The lap exists but has no trace. The message says whether that is because the raw recording is gone (FR-006) or because it needs re-ingesting. |

---

### `GET /api/compare?lap={uid}:{n}&reference={uid}:{n}`

`reference` is optional. When it is omitted, the best counting lap of the `lap`'s session
is used (FR-018).

```json
{
  "lap":       { "...": "the trace object above" },
  "reference": { "...": "the trace object above" },
  "gap": {
    "distance_m": [0, 1, 2],
    "gap_ms":     [0.0, 0.4, 0.9]
  },
  "context": {
    "lap":       { "assists_summary": "TC full, ABS, manual gearbox", "tyre": "Soft", "tyre_age_laps": 1, "weather_name": "overcast", "track_temp_c": 31, "ai_difficulty": 90, "fuel_in_tank_start": 4.1 },
    "reference": { "...": "same fields" },
    "differs":   ["tyre_age_laps", "fuel_in_tank_start"]
  }
}
```

| Status | Code | When |
|---|---|---|
| 400 | `bad_lap_ref` | Not in `uid:n` form |
| 404 | `lap_not_found` | Either lap missing |
| 409 | `different_circuits` | Track ids differ (FR-008). The message names both circuits. |
| 409 | `reference_incomplete` | The reference lap has no complete time (FR-019) |
| 409 | `trace_unavailable` | Either lap has no trace |

---

### `GET /api/sessions/{session_uid}/pace`

Data for the session pace chart (User Story 3). It needs no traces.

```json
{
  "laps":   [ { "lap_number": 1, "lap_time_ms": 76859, "counts": false, "exclusion_reason": "first_lap", "stint_index": 0, "tyre_visual_compound_name": "Soft" } ],
  "stints": [ { "stint_index": 0, "start_lap": 1, "end_lap": 4, "tyre_visual_compound_name": "Soft" } ]
}
```

---

### `GET /api/laps?track_id={id}`

Every lap at a circuit across all sessions, so any two can be picked for comparison
(FR-007). Each row: `session_uid`, `started_at`, `session_type_name`, `lap_number`,
`lap_time_ms`, `counts`, `exclusion_reason`, `has_trace`.
