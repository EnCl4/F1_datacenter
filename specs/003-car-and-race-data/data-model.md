# Phase 1 Data Model: Car and Race Data

All files are per session directory, regenerable from the raw log (principle I), and part
of the idempotence result set. Every table carries `session_uid` (string). Wheels are
always named `_fl`, `_fr`, `_rl`, `_rr`.

## `lap_car.parquet`: one row per lap

| Columns | Type | Source / rule |
|---|---|---|
| `lap_number` | int32 | |
| `tyre_surface_avg_{fl,fr,rl,rr}`, `tyre_surface_max_{…}` | float32 | CarTelemetry, samples before any mid-lap tyre change (R5) |
| `tyre_inner_avg_{…}`, `tyre_inner_max_{…}` | float32 | idem |
| `brake_avg_{…}`, `brake_max_{…}` | float32 | CarTelemetry |
| `pressure_avg_{…}` | float32 | CarTelemetry |
| `engine_temp_max` | float32 | CarTelemetry |
| `tyre_change_in_lap` | bool | tyre age dropped during the lap |
| `ers_start_mj`, `ers_end_mj` | float32 | CarStatus `ers_store_energy`, first and last of the lap |
| `ers_deployed_mj`, `ers_harvested_mj` | float32 | last values **before** the lap changes (R4); harvested = MGU-K + MGU-H |
| `ers_balance_mj` | float32 | harvested − deployed (negative = deficit, FR-008) |
| `ers_modes` | string | distinct modes used, e.g. "1,3" |
| `fuel_start_kg`, `fuel_end_kg`, `fuel_used_kg` | float32 | CarStatus |
| `fuel_mix` | string | distinct values used |
| `brake_bias` | string | distinct values used, e.g. "57,63" |
| `settings_changed` | bool | brake bias, ERS mode or fuel mix differs from the previous lap |
| `damage_{front_left_wing,front_right_wing,rear_wing,floor,diffuser,sidepod,gearbox,engine}` | int16 | CarDamage, max during the lap |
| `damage_increased` | bool | any part higher than at the end of the previous lap |
| `excursions`, `excursion_m` | int16, float32 | count and total length (R3) |
| `drs_pct` | float32 | share of the lap's samples with DRS open |
| `position_at_line` | int16 | LapData car position at lap end |
| `gap_ahead_ms_at_line` | int32 | LapData `deltaToCarInFront` at lap end; null when P1 |
| `corner_warnings`, `penalties_s` | int16 | (already per lap in feature 001; repeated here for one-row-per-lap access) |

## `excursions.parquet`

`lap_number` int32 · `start_m` float32 · `length_m` float32 · `wheels` string ("fl,fr") ·
`surface` string ("grass") · `session_time_s` float32.

## `field.parquet` and `field_laps.parquet`

`field`: `car_idx` int16 · `name` string · `team_id` int16 · `race_number` int16 ·
`ai_controlled` bool · `is_player` bool · `best_lap_ms` int32 · `best_lap_number` int16 ·
`num_laps` int16 · `finish_position` int16 (null if no classification) · `result_status`
string · `stints` string (e.g. "Soft 1-4 · Soft 5-5").
When names are hidden, `name` is `"Driver #<race_number>"` (FR-019).

`field_laps`: `car_idx` int16 · `lap_number` int16 · `lap_time_ms` int32 · `valid` bool.

## `timeline.parquet`

`session_time_s` float32 · `lap_number` int16 · `weather` string · `track_temp_c` int16 ·
`air_temp_c` int16. One row at the start, plus one on every change.

## `events.parquet`

`session_time_s` float32 · `lap_number` int16 · `code` string · `vehicle_idx` int16 ·
`other_vehicle_idx` int16 · `value` float32 (lap time s / speed km/h / penalty s) ·
`involves_player` bool · `description` string (e.g. "VERSTAPPEN overtook STROLL").

## `tyre_sets.parquet`

`set_index` int16 · `actual_compound` string · `visual_compound` string · `wear_pct` int16
· `available` bool · `fitted` bool · `lap_delta_ms` int32 · `life_span` int16 ·
`usable_life` int16. From the last TyreSets packet for the player.

## Trace additions (`traces.parquet`)

`tyre_surface_{fl,fr,rl,rr}`, `tyre_inner_{…}`, `brake_{…}`, `pressure_{…}` (float32,
interpolated), `gap_ahead_ms` (float32, interpolated), `off_track` (float32 0/1,
step-held).
