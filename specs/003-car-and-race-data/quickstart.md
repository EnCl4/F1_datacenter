# Quickstart & Validation: Car and Race Data

1. `python -m f1dc.cli.main ingest`. Existing sessions are re-processed at 1.2.0.
2. Open the reference Interlagos race (2026-09-04). **Expected** (SC-002):
   - front tyre core temperatures 105–107 °C by lap 3, dropping on the out lap
   - battery 3.9 MJ falling to under 0.2 MJ, with deployed exceeding harvested every lap
   - lap 2: **0** excursions; laps 3–5: some, located on the map
   - front-left wing damage **27%**
   - brake bias **57%** on laps 3–4, 63% otherwise, with the change highlighted
   - field: best lap ranked **8th of 20**, fastest 1:10.900, named drivers, VERSTAPPEN = you
   - penalties on laps 1 and 4 (corner-cutting warnings)
3. **Compare laps** → the G-G diagram spans about ±4 g lateral, −4.2 g braking and +1.6 g
   accelerating. Lateral and longitudinal force share one trace.
4. **Delete** (test library only, never the real one): typing a wrong name or cancelling
   deletes nothing; typing the circuit name removes the session and its recording, and
   re-ingest does not bring it back.
5. `pytest` (and `--raw` for the full-capture suite).
