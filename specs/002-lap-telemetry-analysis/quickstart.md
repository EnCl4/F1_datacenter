# Quickstart & Validation Guide

**Feature**: `002-lap-telemetry-analysis`

## 1. Existing recordings gain traces (SC-004)

```bash
python -m f1dc.cli.main ingest
```

**Expected**: the reference race is re-processed (ingest version 1.1.0), and
`C:\F1Data\derived\sessions\<uid>\traces.parquet` appears. No driving needed.

## 2. Compare two laps (US1, US2)

Double-click **F1 Data Center - Library** → open the Interlagos race → **Compare**.

**Expected**:

- lap 2 is preselected as the reference: the best counting lap (FR-018)
- choosing lap 5 draws speed, throttle, brake, steering, gear, revs and g-forces for both
  laps, stacked and aligned by distance
- pointing at a chart marks the same place on every chart and on the map
- dragging to zoom on one chart zooms them all
- at about **2,300 m**, lap 5 shows higher minimum speed in a lower gear than lap 2, the
  difference found during design
- the time gap line ends at **+1.203 s** (72.642 − 71.439)

## 3. Session pace (US3)

**Expected**: five laps in order, two Soft stints marked (laps 1–4, lap 5), and laps 1, 3, 4
and 5 visibly marked as not counting, each with its reason.

## 4. Circuit map (US4)

**Expected**: the outline of Interlagos, closed into a loop, colourable by speed, throttle
or brake.

## 5. Regression and precision

```bash
pytest
pytest tests/integration/test_trace_precision.py --raw C:/F1Data/raw/<capture>.f1raw
```

**Expected**: all pass. The precision suite checks the time gap at the line within 50 ms
(SC-002) and braking points within 5 m across laps (SC-003), on full-rate data.

## 6. Refusals

```text
/api/compare?lap=<interlagos uid>:2&reference=<another circuit's uid>:3   -> 409 different_circuits
```
