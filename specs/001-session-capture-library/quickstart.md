# Quickstart & Validation Guide

**Feature**: `001-session-capture-library` | **Date**: 2026-09-04

Runnable scenarios that prove the feature works end to end. Each maps to specific
requirements so a reviewer can see what is being demonstrated rather than inferring it.

---

## Prerequisites

| | |
|---|---|
| OS | Windows 10/11 |
| Python | 3.13+ |
| Node | 22+ (frontend only) |
| Game | F1 23, telemetry enabled |
| Data dir | `C:\F1Data` — **not** inside OneDrive or any sync root |

In-game: **Settings → Telemetry Settings** — UDP Telemetry `On`, Broadcast `Off`,
IP `127.0.0.1`, Port `20777`, Send Rate `60 Hz`, Format `2023`.

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

---

## Scenario 1 — Environment check, no game required

**Validates**: FR-004, FR-005, FR-006 · CLI contract

```bash
f1dc doctor
```

**Expected**: reports the data directory as writable and not a sync root, free disk space,
and the UDP port as bindable. With the game running and on track, it additionally reports
packet rates and sizes, with observed sizes matching the expected 2023 wire sizes.

**Negative case**: run `f1dc record` in one terminal and `f1dc doctor` in another — the port
check must report the conflict clearly rather than silently capturing nothing.

---

## Scenario 2 — Start recording in one action

**Validates**: FR-001, FR-025, FR-026 · SC-001, SC-010

Double-click the **F1 Data Center** desktop shortcut. No terminal.

**Expected**: a window appears within 5 seconds showing **Listening**. No command line is
involved at any point.

Enter a session in the game.

**Expected**: within ~1 second the window changes to **Recording — Interlagos, Race** and
shows the current lap. A reviewer glancing at the window can tell the state in under
2 seconds.

---

## Scenario 3 — One start covers a whole sitting

**Validates**: FR-028, FR-007 · User Story 1 scenarios 2 and 6

With the recorder still running from Scenario 2, complete a practice session, return to the
menus, then complete a race. Do not touch the app in between.

**Expected**: two raw logs in `C:\F1Data\raw\`, one per session, neither truncated nor
merged. Menu navigation between them produces **no** third file entry in the library —
`sessionUID == 0` traffic is discarded at ingest.

---

## Scenario 4 — Late start is announced, not hidden

**Validates**: FR-027 · User Story 1 scenario 7 · Edge case "started midway"

Close the recorder. Start a race and complete two laps. *Now* start the recorder.

**Expected**: the window shows a visible warning that a session is already under way and
earlier data was not captured. The resulting session is flagged `started_late` and appears
marked in the library.

---

## Scenario 5 — Interpret and browse

**Validates**: FR-008 to FR-014, FR-018 to FR-023

```bash
f1dc ingest --all
f1dc serve --open
```

**Expected**: the library lists every session, most recent first, each showing circuit,
session type, date, conditions and best lap. Filtering by circuit, category and date range
narrows the list. Opening a session shows every lap with times, sector times, tyre compound
and age, and whether the lap counted — alongside the assists, weather, temperatures and
difficulty that make those times comparable.

---

## Scenario 6 — Idempotence

**Validates**: FR-015, FR-016 · SC-005 · Constitution principle VII

```bash
f1dc ingest --all
sha256sum C:/F1Data/derived/sessions/*/laps.parquet > /tmp/before.txt
f1dc ingest --all --force
sha256sum C:/F1Data/derived/sessions/*/laps.parquet > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```

**Expected**: `diff` reports no differences, and the session count in
`GET /api/health` is unchanged. Re-ingesting must never duplicate a library entry.

---

## Scenario 7 — Regression against real captured bytes

**Validates**: Constitution principle IV · R8, R11

```bash
pytest tests/unit tests/contract
```

**Expected**: all pass, including the named hazard cases:

- every codec's field sizes sum to its documented wire size
- sector times are recombined as `minutes × 60000 + ms` and do not wrap above 65.535 s
- `m_lastLapTimeInMS` is attributed to lap *N − 1*, not lap *N*
- wheel arrays map rear-left, rear-right, front-left, front-right
- lap times derived from `LapData` equal those in `SessionHistory`

The full 229 MB calibration capture drives an additional end-to-end test:

```bash
pytest tests/integration --raw C:/F1Data/raw/calibration.bin
```

**Expected**, from the known-good reference race — Interlagos, Race, 5 laps, overcast,
31 °C track, 24 °C air, AI 90, manual gearbox, no steering or braking assist, pit-release
assist on, **traction control full and ABS on**:

| Lap | Time | Note |
|---:|---|---|
| 1 | 1:16.859 | first lap, excluded from pace |
| 2 | 1:11.439 | counts |
| 3 | 1:19.146 | in-lap, pit stop |
| 4 | 1:12.642 | out-lap excluded |

Two `sessionUID` values are present; the one equal to `0` must not appear in the library.

---

## Scenario 8 — The validity rule actually branches

**Validates**: FR-012, FR-024 · SC-008 · Constitution principle VI

```bash
pytest tests/unit/test_lap_validity.py -v
```

**Expected**: for a **race**, a lap with corner-cutting warnings but no invalidation flag is
still excluded from pace statistics when it is an in-lap, out-lap or first lap — and is
**never** returned as a personal best. For **qualifying**, the game's invalidation flag is
the deciding rule.

This is the case that motivated the branch: the reference race contains zero invalidated
laps across all 22 cars while the player accumulated two corner-cutting warnings. A single
rule would call every race lap clean.

---

## Scenario 9 — The library admits when nothing is recording

**Validates**: FR-029 · Edge case "driver forgets to start the recorder"

Stop the recorder. Reload the library.

**Expected**: a clearly visible banner states that nothing is currently being recorded. Kill
the recorder process abruptly rather than closing it cleanly — the banner must still appear
within 10 seconds, because a stale status file is treated as stopped.
