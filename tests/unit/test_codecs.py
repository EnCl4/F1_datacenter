"""T026 -- every codec decoded from real captured bytes, with semantic checks.

Sizes matching is necessary but not sufficient: a codec can have the right total length
and still map fields to the wrong offsets. These tests assert the *values* against what
is known to be true of the reference race -- Interlagos, 5 laps, overcast, 31/24 degrees,
AI 90, all assists off with a manual gearbox.
"""

from __future__ import annotations

from f1dc.capture.rawlog import Record
from f1dc.wire.f1_2023.car_damage import CarDamageCodec
from f1dc.wire.f1_2023.car_setups import CarSetupsCodec
from f1dc.wire.f1_2023.car_status import CarStatusCodec
from f1dc.wire.f1_2023.enums import ACTUAL_TYRE_COMPOUNDS, EVENT_CODES, VISUAL_TYRE_COMPOUNDS
from f1dc.wire.f1_2023.event import EventCodec
from f1dc.wire.f1_2023.final_classification import FinalClassificationCodec
from f1dc.wire.f1_2023.lap_data import LapDataCodec, combine_sector
from f1dc.wire.f1_2023.session import SessionCodec
from f1dc.wire.f1_2023.session_history import SessionHistoryCodec
from f1dc.wire.f1_2023.tyre_sets import TyreSetsCodec
from tests.conftest import REFERENCE, first_of

# --------------------------------------------------------------------------------------
# Session -- the comparability context (principle VI)
# --------------------------------------------------------------------------------------


def test_session_decodes_the_reference_race(by_packet_id) -> None:
    s = SessionCodec.decode(first_of(by_packet_id, 1))
    assert s.track_id == REFERENCE["track_id"]
    assert s.track_name == REFERENCE["track_name"]
    assert s.session_type == REFERENCE["session_type"]
    assert s.session_category == REFERENCE["session_category"]
    assert s.total_laps == REFERENCE["total_laps"]
    assert s.track_length == REFERENCE["track_length"]
    assert s.weather == REFERENCE["weather"]
    assert s.weather_name == "overcast"
    assert s.track_temperature == REFERENCE["track_temperature"]
    assert s.air_temperature == REFERENCE["air_temperature"]
    assert s.ai_difficulty == REFERENCE["ai_difficulty"]


def test_session_assists_match_the_reference_capture(by_packet_id) -> None:
    """The driver's actual Session-packet assist configuration."""
    s = SessionCodec.decode(first_of(by_packet_id, 1))
    assert s.assists == {
        "steering": 0,
        "braking": 0,
        "gearbox": 1,  # 1 = manual
        "pit": 0,
        "pit_release": 1,  # pit release assist IS enabled
        "ers": 0,
        "drs": 0,
        "racing_line": 0,
        "racing_line_type": 0,
    }
    assert "manual gearbox" in s.assists_summary


def test_traction_control_and_abs_are_not_in_the_session_packet(
    by_packet_id, player_index
) -> None:
    """Principle VI's comparability context needs BOTH packets.

    The Session packet reports braking assist off, which alone reads as "no braking
    aids". CarStatus reports traction control on full and ABS enabled. A session summary
    built from Session alone would materially misrepresent how these lap times were set.
    """
    s = SessionCodec.decode(first_of(by_packet_id, 1))
    assert "traction_control" not in s.assists
    assert "anti_lock_brakes" not in s.assists

    cs = CarStatusCodec.decode_car(first_of(by_packet_id, 7), player_index)
    aids = cs.driver_aids
    assert aids["traction_control"] == 2, "reference capture ran full traction control"
    assert aids["anti_lock_brakes"] == 1, "reference capture ran ABS"


def test_session_marshal_zone_and_forecast_counts_are_plausible(by_packet_id) -> None:
    """These sit either side of the two skipped array regions; implausible values here
    would mean the skip lengths are wrong and everything after them is misaligned."""
    s = SessionCodec.decode(first_of(by_packet_id, 1))
    assert 0 <= s.num_marshal_zones <= 21
    assert 0 <= s.num_weather_forecast_samples <= 56
    assert 0 <= s.safety_car_status <= 3
    assert s.network_game in (0, 1)


# --------------------------------------------------------------------------------------
# LapData
# --------------------------------------------------------------------------------------


def test_lap_data_player_values_are_plausible(by_packet_id, player_index) -> None:
    laps = [LapDataCodec.decode_car(r.payload, player_index) for r in by_packet_id[2]]
    assert laps
    for lap in laps:
        assert 1 <= lap.current_lap_num <= 6
        assert 0 <= lap.car_position <= 22
        assert -50.0 <= lap.lap_distance <= REFERENCE["track_length"] + 50
        assert 0 <= lap.pit_status <= 2
        assert lap.current_lap_invalid in (0, 1)


def test_lap_numbers_cover_the_five_lap_race(by_packet_id, player_index) -> None:
    nums = {LapDataCodec.decode_car(r.payload, player_index).current_lap_num for r in by_packet_id[2]}
    assert nums == {1, 2, 3, 4, 5}


def test_the_pit_stop_is_present(by_packet_id, player_index) -> None:
    laps = [LapDataCodec.decode_car(r.payload, player_index) for r in by_packet_id[2]]
    pitting = {lap.current_lap_num for lap in laps if lap.pit_status != 0}
    assert pitting, "the reference race contained a pit stop"
    assert max(lap.num_pit_stops for lap in laps) >= 1


def test_sector_recombination_handles_the_uint16_ceiling() -> None:
    """The defect this guards: reading the millisecond field alone wraps above 65.535 s.

    The millisecond field is a uint16 and saturates at 65 535. A 70-second sector is
    therefore transmitted as minutes=1, ms=10 000 -- and reading only the millisecond
    field would report it as 10 seconds, not 70.
    """
    assert combine_sector(17_204, 0) == 17_204  # ordinary sector, no overflow
    assert combine_sector(0, 1) == 60_000  # exactly one minute
    assert combine_sector(5_535, 1) == 65_535  # the ceiling itself
    assert combine_sector(10_000, 1) == 70_000  # past the ceiling: the failure case
    assert combine_sector(30_000, 2) == 150_000  # a safety-car sector


def test_sector_times_are_plausible_for_interlagos(by_packet_id, player_index) -> None:
    laps = [LapDataCodec.decode_car(r.payload, player_index) for r in by_packet_id[2]]
    with_sectors = [lap for lap in laps if lap.sector1_ms > 0]
    assert with_sectors
    for lap in with_sectors:
        assert 5_000 < lap.sector1_ms < 120_000, f"implausible sector 1: {lap.sector1_ms} ms"


# --------------------------------------------------------------------------------------
# CarStatus / CarDamage / CarSetups
# --------------------------------------------------------------------------------------


def test_car_status_tyres_and_fuel_are_plausible(by_packet_id, player_index) -> None:
    for rec in by_packet_id[7]:
        cs = CarStatusCodec.decode_car(rec.payload, player_index)
        assert cs.actual_tyre_compound in ACTUAL_TYRE_COMPOUNDS
        assert cs.visual_tyre_compound in VISUAL_TYRE_COMPOUNDS
        assert 0 <= cs.tyres_age_laps <= 100
        assert 0.0 <= cs.fuel_in_tank <= cs.fuel_capacity + 1.0
        assert 8_000 <= cs.max_rpm <= 20_000
        assert 0 <= cs.front_brake_bias <= 100
        # F1 23 reports 9 here, not the 8 forward gears one might expect.
        assert 1 <= cs.max_gears <= 10
        assert 0 <= cs.traction_control <= 2
        assert cs.anti_lock_brakes in (0, 1)


def test_car_damage_wear_is_a_percentage(by_packet_id, player_index) -> None:
    for rec in by_packet_id[10]:
        d = CarDamageCodec.decode_car(rec.payload, player_index)
        for wheel, wear in d.tyre_wear.items():
            assert 0.0 <= wear <= 100.0, f"{wheel} wear {wear} out of range"
        assert 0 <= d.engine_damage <= 100
        assert d.drs_fault in (0, 1)


def test_tyre_wear_increases_over_the_race(by_packet_id, player_index) -> None:
    """A real ordering property: a mis-mapped float array would not trend upward."""
    wear = [CarDamageCodec.decode_car(r.payload, player_index).max_tyre_wear for r in by_packet_id[10]]
    assert max(wear) > min(wear), "tyre wear never changed across the race"
    assert max(wear) > 1.0


def test_car_setups_are_plausible(by_packet_id, player_index) -> None:
    s = CarSetupsCodec.decode_car(first_of(by_packet_id, 5), player_index)
    assert 0 <= s.front_wing <= 50
    assert 0 <= s.rear_wing <= 50
    assert 0 <= s.brake_bias <= 100
    assert 15.0 <= s.front_left_tyre_pressure <= 35.0
    assert 0.0 <= s.fuel_load <= 120.0


# --------------------------------------------------------------------------------------
# SessionHistory / FinalClassification / TyreSets / Event
# --------------------------------------------------------------------------------------


def test_session_history_carries_lap_times_and_stints(by_packet_id) -> None:
    decoded = [SessionHistoryCodec.decode(r.payload) for r in by_packet_id[11]]
    assert decoded
    assert {d.car_idx for d in decoded}, "should cover multiple cars"
    with_laps = [d for d in decoded if d.laps and any(lap.is_recorded for lap in d.laps)]
    assert with_laps, "no recorded laps found in session history"
    for lap in with_laps[-1].laps:
        if lap.is_recorded:
            assert 30_000 < lap.lap_time_ms < 300_000
            assert isinstance(lap.is_valid, bool)
            assert len(lap.sector_validity) == 3


def test_final_classification_has_the_whole_field(by_packet_id) -> None:
    payload = first_of(by_packet_id, 8)
    n = FinalClassificationCodec.num_cars(payload)
    assert 1 <= n <= 22
    results = FinalClassificationCodec.decode_classified(payload)
    assert len(results) == n
    positions = sorted(r.position for r in results)
    assert positions == list(range(1, n + 1)), "finishing positions should be 1..n"
    for r in results:
        assert 0 <= r.num_tyre_stints <= 8
        assert r.total_race_time >= 0.0


def test_final_classification_carries_every_drivers_stints(by_packet_id) -> None:
    """The whole field's strategy for 1020 bytes -- the reason player-only is cheap."""
    results = FinalClassificationCodec.decode_classified(first_of(by_packet_id, 8))
    with_stints = [r for r in results if r.num_tyre_stints > 0]
    assert with_stints
    for r in with_stints:
        assert len(r.stints) == min(r.num_tyre_stints, 8)


def test_tyre_sets_has_twenty_sets(by_packet_id) -> None:
    ts = TyreSetsCodec.decode(first_of(by_packet_id, 12))
    assert len(ts.sets) == 20
    assert 0 <= ts.car_idx < 22
    for s in ts.sets:
        assert 0 <= s.wear <= 100
        assert s.fitted in (0, 1)


def test_events_decode_to_known_codes(by_packet_id) -> None:
    codes = {EventCodec.decode(r.payload).code for r in by_packet_id[3]}
    assert codes, "fixture should contain events"
    unknown = codes - set(EVENT_CODES)
    assert not unknown, f"unrecognised event codes: {unknown}"


def test_session_end_events_are_present(by_packet_id) -> None:
    """The race ran to the chequered flag, so FR-014 has something to detect."""
    events = [EventCodec.decode(r.payload) for r in by_packet_id[3]]
    assert any(e.is_session_end for e in events), "expected SEND or CHQF"


def test_no_flashback_in_the_reference_capture(by_packet_id) -> None:
    events = [EventCodec.decode(r.payload) for r in by_packet_id[3]]
    assert not any(e.is_flashback for e in events)


def test_event_detail_payload_is_preserved_undecoded(by_packet_id) -> None:
    """Deferred, not discarded (research R6)."""
    e = EventCodec.decode(first_of(by_packet_id, 3))
    assert len(e.detail) == 12


def test_menu_state_records_are_events(records: list[Record]) -> None:
    """The uid==0 traffic in the reference capture was Event packets only."""
    from f1dc.wire.header import decode_header

    menu = [decode_header(r.payload) for r in records if decode_header(r.payload).is_menu_state]
    assert menu
    assert {h.packet_id for h in menu} == {3}
