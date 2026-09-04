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
