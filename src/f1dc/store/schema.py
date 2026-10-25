"""T053 -- Parquet schemas for the derived store.

Written explicitly rather than inferred, because inference would silently change column
types when a session happens to contain only nulls in a column -- and a schema that
shifts between sessions makes the DuckDB views unreadable.

``session_uid`` is a string throughout: it is a uint64 in the wire format, which exceeds
what JSON and several engines handle without loss.
"""

from __future__ import annotations

import pyarrow as pa

SESSION_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("recording_id", pa.string()),
        ("started_at", pa.string()),
        ("ended_at", pa.string()),
        ("duration_s", pa.float64()),
        ("track_id", pa.int16()),
        ("track_name", pa.string()),
        ("track_length_m", pa.int32()),
        ("session_type", pa.int16()),
        ("session_type_name", pa.string()),
        ("session_category", pa.string()),
        ("total_laps", pa.int16()),
        ("weather", pa.int16()),
        ("weather_name", pa.string()),
        ("air_temp_c", pa.int16()),
        ("track_temp_c", pa.int16()),
        ("ai_difficulty", pa.int16()),
        ("formula", pa.int16()),
        ("game_mode", pa.int16()),
        ("rule_set", pa.int16()),
        ("network_game", pa.bool_()),
        ("player_car_index", pa.int16()),
        ("ended_naturally", pa.bool_()),
        ("end_reason", pa.string()),
        ("started_late", pa.bool_()),
        ("num_laps", pa.int32()),
        ("num_counting_laps", pa.int32()),
        ("best_lap_ms", pa.int32()),
        ("best_lap_number", pa.int32()),
        ("loss_pct", pa.float64()),
        ("ingest_version", pa.string()),
        # Assists: nine from the Session packet...
        ("assist_steering", pa.int16()),
        ("assist_braking", pa.int16()),
        ("assist_gearbox", pa.int16()),
        ("assist_pit", pa.int16()),
        ("assist_pit_release", pa.int16()),
        ("assist_ers", pa.int16()),
        ("assist_drs", pa.int16()),
        ("assist_racing_line", pa.int16()),
        ("assist_racing_line_type", pa.int16()),
        # ...and two that exist only in CarStatus.
        ("assist_traction_control", pa.int16()),
        ("assist_anti_lock_brakes", pa.int16()),
        ("assists_summary", pa.string()),
        ("incomplete", pa.bool_()),
    ]
)

STINT_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("stint_index", pa.int32()),
        ("start_lap", pa.int32()),
        ("end_lap", pa.int32()),
        ("tyre_actual_compound", pa.int16()),
        ("tyre_actual_compound_name", pa.string()),
        ("tyre_visual_compound", pa.int16()),
        ("tyre_visual_compound_name", pa.string()),
        ("tyre_age_start_laps", pa.int32()),
        ("num_laps", pa.int32()),
    ]
)

LAP_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("lap_number", pa.int32()),
        ("stint_index", pa.int32()),
        ("lap_time_ms", pa.int32()),
        ("sector1_ms", pa.int32()),
        ("sector2_ms", pa.int32()),
        ("sector3_ms", pa.int32()),
        ("valid", pa.bool_()),
        ("sector1_valid", pa.bool_()),
        ("sector2_valid", pa.bool_()),
        ("sector3_valid", pa.bool_()),
        ("counts", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("is_in_lap", pa.bool_()),
        ("is_out_lap", pa.bool_()),
        ("pit_status", pa.int16()),
        ("num_pit_stops", pa.int32()),
        ("under_safety_car", pa.bool_()),
        ("tyre_actual_compound", pa.int16()),
        ("tyre_actual_compound_name", pa.string()),
        ("tyre_visual_compound", pa.int16()),
        ("tyre_visual_compound_name", pa.string()),
        ("tyre_age_laps", pa.int32()),
        ("fuel_in_tank_start", pa.float64()),
        ("fuel_remaining_laps", pa.float64()),
        # Named per wheel, never positional: F1 23 orders wheel arrays rear-left first.
        ("tyre_wear_rl", pa.float64()),
        ("tyre_wear_rr", pa.float64()),
        ("tyre_wear_fl", pa.float64()),
        ("tyre_wear_fr", pa.float64()),
        ("car_position", pa.int16()),
        ("penalties_s", pa.int16()),
        ("corner_cutting_warnings", pa.int16()),
        ("sector_sum_mismatch", pa.bool_()),
        ("history_mismatch", pa.bool_()),
        # Track distance where sectors 2 and 3 begin (feature 002, FR-013). Measured on the
        # reference race: 1 167.5-1 168.4 m and 3 113.3-3 114.3 m across laps.
        ("sector2_start_m", pa.float32()),
        ("sector3_start_m", pa.float32()),
    ]
)

#: Wheel suffixes, in the order every per-wheel column group is written.
_WHEELS = ("fl", "fr", "rl", "rr")


def _wheels(prefix: str, dtype: pa.DataType) -> list[tuple[str, pa.DataType]]:
    """One column per wheel: ``prefix_fl``, ``prefix_fr``, ``prefix_rl``, ``prefix_rr``."""
    return [(f"{prefix}_{wheel}", dtype) for wheel in _WHEELS]


# Per-metre lap traces (feature 002). Every channel is null inside a recording gap, so a
# gap reads as missing data rather than as a flat line at zero.
TRACE_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("lap_number", pa.int32()),
        ("distance_m", pa.int32()),
        ("time_ms", pa.float32()),
        ("speed_kph", pa.float32()),
        ("throttle", pa.float32()),
        ("brake", pa.float32()),
        ("steer", pa.float32()),
        ("gear", pa.float32()),
        ("rpm", pa.float32()),
        ("drs", pa.float32()),
        ("g_lat", pa.float32()),
        ("g_lon", pa.float32()),
        ("x", pa.float32()),
        ("z", pa.float32()),
        *_wheels("tyre_surface", pa.float32()),
        *_wheels("tyre_inner", pa.float32()),
        *_wheels("brake", pa.float32()),
        *_wheels("pressure", pa.float32()),
        ("gap_ahead_ms", pa.float32()),
        ("off_track", pa.float32()),
    ]
)

# Per-lap car summary (feature 003): CarTelemetry, CarStatus and CarDamage folded to one
# row per lap for the player.
LAP_CAR_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("lap_number", pa.int32()),
        *_wheels("tyre_surface_avg", pa.float32()),
        *_wheels("tyre_surface_max", pa.float32()),
        *_wheels("tyre_inner_avg", pa.float32()),
        *_wheels("tyre_inner_max", pa.float32()),
        *_wheels("brake_avg", pa.float32()),
        *_wheels("brake_max", pa.float32()),
        *_wheels("pressure_avg", pa.float32()),
        ("engine_temp_max", pa.float32()),
        ("tyre_change_in_lap", pa.bool_()),
        ("ers_start_mj", pa.float32()),
        ("ers_end_mj", pa.float32()),
        ("ers_deployed_mj", pa.float32()),
        ("ers_harvested_mj", pa.float32()),
        ("ers_balance_mj", pa.float32()),
        ("ers_modes", pa.string()),
        ("fuel_start_kg", pa.float32()),
        ("fuel_end_kg", pa.float32()),
        ("fuel_used_kg", pa.float32()),
        ("fuel_mix", pa.string()),
        ("brake_bias", pa.string()),
        ("settings_changed", pa.bool_()),
        ("damage_front_left_wing", pa.int16()),
        ("damage_front_right_wing", pa.int16()),
        ("damage_rear_wing", pa.int16()),
        ("damage_floor", pa.int16()),
        ("damage_diffuser", pa.int16()),
        ("damage_sidepod", pa.int16()),
        ("damage_gearbox", pa.int16()),
        ("damage_engine", pa.int16()),
        ("damage_increased", pa.bool_()),
        ("excursions", pa.int16()),
        ("excursion_m", pa.float32()),
        ("drs_pct", pa.float32()),
        ("position_at_line", pa.int16()),
        ("gap_ahead_ms_at_line", pa.int32()),
        ("corner_warnings", pa.int16()),
        ("penalties_s", pa.int16()),
    ]
)

# Track excursions (feature 003, research R3): one row per run of off-track samples.
EXCURSION_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("lap_number", pa.int32()),
        ("start_m", pa.float32()),
        ("length_m", pa.float32()),
        ("wheels", pa.string()),
        ("surface", pa.string()),
        ("session_time_s", pa.float32()),
    ]
)

# Whole-field classification (feature 003): one row per car.
FIELD_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("car_idx", pa.int16()),
        ("name", pa.string()),
        ("team_id", pa.int16()),
        ("race_number", pa.int16()),
        ("ai_controlled", pa.bool_()),
        ("is_player", pa.bool_()),
        ("best_lap_ms", pa.int32()),
        ("best_lap_number", pa.int16()),
        ("num_laps", pa.int16()),
        ("finish_position", pa.int16()),
        ("result_status", pa.string()),
        ("stints", pa.string()),
    ]
)

# Every car's lap times (feature 003), one row per completed lap.
FIELD_LAPS_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("car_idx", pa.int16()),
        ("lap_number", pa.int16()),
        ("lap_time_ms", pa.int32()),
        ("valid", pa.bool_()),
    ]
)

# Session-wide conditions over time (feature 003): a row at start and on every change.
TIMELINE_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("session_time_s", pa.float32()),
        ("lap_number", pa.int16()),
        ("weather", pa.string()),
        ("track_temp_c", pa.int16()),
        ("air_temp_c", pa.int16()),
    ]
)

# Race events with their decoded detail (feature 003, see EventCodec.parsed).
EVENT_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("session_time_s", pa.float32()),
        ("lap_number", pa.int16()),
        ("code", pa.string()),
        ("vehicle_idx", pa.int16()),
        ("other_vehicle_idx", pa.int16()),
        ("value", pa.float32()),
        ("involves_player", pa.bool_()),
        ("description", pa.string()),
    ]
)

# The player's tyre allocation (feature 003): one row per tyre set.
TYRE_SET_SCHEMA = pa.schema(
    [
        ("session_uid", pa.string()),
        ("set_index", pa.int16()),
        ("actual_compound", pa.string()),
        ("visual_compound", pa.string()),
        ("wear_pct", pa.int16()),
        ("available", pa.bool_()),
        ("fitted", pa.bool_()),
        ("lap_delta_ms", pa.int32()),
        ("life_span", pa.int16()),
        ("usable_life", pa.int16()),
    ]
)

RECORDING_SCHEMA = pa.schema(
    [
        ("recording_id", pa.string()),
        ("path", pa.string()),
        ("captured_at", pa.string()),
        ("size_bytes", pa.int64()),
        ("packets_received", pa.int64()),
        ("frames_lost", pa.int64()),
        ("loss_pct", pa.float64()),
        ("queue_high_water", pa.int32()),
        ("packet_format", pa.int32()),
        ("game_version", pa.string()),
        ("unknown_packets", pa.int64()),
        ("compressed", pa.bool_()),
        ("starred", pa.bool_()),
        ("ingest_version", pa.string()),
        ("ingested_at", pa.string()),
    ]
)


def table_from_rows(rows: list[dict], schema: pa.Schema) -> pa.Table:
    """Build a table with the declared schema, filling absent columns with nulls."""
    columns = {name: [row.get(name) for row in rows] for name in schema.names}
    return pa.Table.from_pydict(columns, schema=schema)
