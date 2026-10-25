# Contract: HTTP API additions (feature 003)

Errors keep the shape `{"error": {"code", "message"}}`; 409 messages are shown verbatim.

## Read routes

| Route | Returns |
|---|---|
| `GET /api/sessions/{uid}/car` | `{"laps": [ <lap_car row> … ]}`, ordered by lap |
| `GET /api/sessions/{uid}/excursions` | `{"items": [ <excursion row> … ]}` |
| `GET /api/sessions/{uid}/field` | `{"cars": [ <field row> … ] ranked by best_lap_ms, "player_rank": 8, "laps": [ <field_laps row> … ]}` |
| `GET /api/sessions/{uid}/timeline` | `{"conditions": [ <timeline row> … ], "events": [ <event row> … ]}` |
| `GET /api/sessions/{uid}/tyre-sets` | `{"items": [ <tyre set row> … ]}` |

Row shapes are exactly the columns in [data-model.md](../data-model.md), without
`session_uid`. Lap traces (`…/laps/{n}/trace`) gain the trace columns listed there.

A session ingested before 1.2.0 returns `409 data_unavailable` from these routes, with a
message saying to run ingest. It never returns empty lists that look like "no data".

## The one write route

### `DELETE /api/sessions/{uid}?confirm={circuit name}`

Permanently deletes the session (constitution 1.1.0, Technology Constraints).

```json
{ "deleted": true, "session_uid": "…",
  "removed": ["C:/F1Data/raw/2026-…_uid.f1raw", "C:/F1Data/derived/sessions/uid"],
  "left_behind": [] }
```

| Status | Code | When |
|---|---|---|
| 400 | `confirmation_required` | `confirm` missing or empty |
| 400 | `confirmation_mismatch` | `confirm` ≠ circuit name (case-insensitive, trimmed) |
| 404 | `session_not_found` | |
| 409 | `session_recording` | it is the session being recorded now |
| 409 | `shared_recording` | its raw log also holds another session |
| 409 | `busy` | ingest is running (write lock held) |
| 500 | `partial_delete` | tombstoned but not fully removed; body lists `removed` and `left_behind` |

**Contract test**: the OpenAPI schema exposes `GET` routes plus exactly **one** `DELETE`,
on this path. Any other write route fails the test (constitution 1.1.0).

## CLI parity

`f1dc delete <session_uid> --confirm <circuit name>`, with the same rules and exit 0 on
success, 2 on a refused confirmation, 3 on any other refusal.
