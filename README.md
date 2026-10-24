# F1 Data Center

Capture the telemetry F1 23 broadcasts, keep it forever, and browse what you have driven —
with the context needed to know whether two lap times are actually comparable.

Windows · Python 3.13+ · fully local, no accounts, no cloud.

---

## Why it works the way it does

F1 23 broadcasts telemetry over UDP **once**. There is no replay and no backfill: a session
you do not capture is gone permanently. Nearly every design decision follows from that.

- **Raw capture is the system of record.** Every datagram is written to disk verbatim
  before anything interprets it, including packet types this software cannot yet decode.
  Everything else is regenerable by re-running ingest.
- **The recorder does nothing but receive and write.** No parsing, no database, no
  compression, no UI. Those all happen in other processes, so the one component whose
  failure is unrecoverable stays as simple as possible.
- **Lap times are never shown without their context.** Assists, tyre, fuel, weather and
  difficulty travel with every lap time, because a 1:11 with traction control is not the
  same achievement as a 1:11 without it.

The full reasoning lives in [the project constitution](.specify/memory/constitution.md).

## Setup

### 1. Turn on telemetry in the game

**Settings → Telemetry Settings:**

| Setting | Value |
|---|---|
| UDP Telemetry | On |
| UDP Broadcast Mode | Off |
| UDP IP Address | 127.0.0.1 |
| UDP Port | 20777 |
| UDP Send Rate | **60 Hz** |
| UDP Format | 2023 |

> **Why 60 and not 120?** Measured on a real capture: at the 120 Hz setting the game
> actually emits ~108 packets/second, and **36% of them are byte-identical repeats** — the
> underlying values only change about 69 times a second. 60 Hz gives you a sample every
> 0.4–0.9 m through the braking zones, finer than the 1 m grid analysis uses, for 36% less
> disk.

### 2. Install

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
```

### 3. Make the desktop shortcut

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1
```

## Daily use

1. **Double-click "F1 Data Center"** before you start playing. A small window appears
   showing **Listening**, then **Recording — Interlagos, Race** once you are on track.
   It captures every session until you close it.
2. Play.
3. When you want to look at the data:

```bash
f1dc ingest      # interpret new recordings
f1dc serve --open
```

> ⚠️ Recording is **started by hand**, by design. Nothing runs in the background. The
> trade-off is real: a session driven before you start the recorder cannot be recovered.
> The window makes its state obvious, and warns you if you started mid-session.

## Analysing laps

Open a session and click **Compare laps**. You get:

- **Session pace**: every lap time in order, tyre stints shaded, and laps that don't count
  shown hollow with the reason. Click a lap to compare it.
- **Time gap**: how far ahead or behind the reference lap you are, metre by metre. Where
  the line climbs, you're losing time. The reference defaults to the session's best
  counting lap.
- **Circuit map**: drawn from your own car's positions, coloured by speed, throttle or
  brake. Wherever you point on a chart, the map marks the same spot.
- **Traces**: speed, throttle, brake, steering, gear, revs and g-forces for both laps,
  aligned by distance. Point anywhere and every chart follows; drag to zoom them all.

Any two laps at the **same circuit** can be compared, across sessions. Their conditions
are shown side by side, with anything that changes lap time highlighted (assists, tyres,
fuel, weather). Laps from different circuits can't be compared, because metre 2,300 at
Monza isn't metre 2,300 at Interlagos.

Gaps in a recording show as gaps; nothing is drawn across missing data. Sessions recorded
before charts existed gain them by re-running `f1dc ingest`, with no re-driving.

## Where your data lives

```
C:\F1Data\
├── raw\        the untouched wire stream, one file per session
└── derived\    interpreted sessions, laps and stints (Parquet)
```

**Never put this inside OneDrive, Dropbox or Google Drive.** Capture writes about
1.3 GB/hour; a sync client will fight the recorder for the open file and upload every byte.
The app refuses a synced folder unless you explicitly override it.

Raw logs are large but they are the reason a future version can re-analyse sessions you
recorded today. `f1dc prune` deletes old ones, and is **never run automatically**.

## Commands

| Command | What it does |
|---|---|
| `f1dc record` | The headless recorder (the shortcut runs this for you) |
| `f1dc launch` | The recorder window |
| `f1dc ingest [--all] [--force]` | Interpret raw logs. Safe to re-run: identical input gives identical output |
| `f1dc serve [--open]` | Local web app on 127.0.0.1:8420 |
| `f1dc doctor` | "Why isn't it recording?" — checks disk, port, folder, and live packet rates |
| `f1dc prune --older-than 90d` | Delete old raw logs. Never automatic |
| `f1dc star <session_uid>` | Keep a session's raw log permanently |

## Development

```bash
pytest                       # unit + contract + integration
pytest --raw C:/F1Data/raw/<capture>.f1raw   # also the full-capture end-to-end tests
cd frontend && npm install && npm run build
```

Tests run against `tests/fixtures/calibration_slice.f1raw` — a 3.4 MB slice of a real
five-lap race at Interlagos, subsampled to preserve every lap transition and the pit stop.
No parser is accepted on the strength of a specification alone; they are all checked
against those bytes.

Its measured packet loss is high on purpose — it *is* missing frames — so tests assert on
lap content rather than loss figures.

## Status

Implemented: feature 001 (capture, ingest, session library) and feature 002 (lap
telemetry analysis). Planned: progression across sessions, race and strategy analysis, and
a setup notebook.
