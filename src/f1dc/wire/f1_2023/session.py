"""T015 -- PacketSessionData, 644 bytes.

Carries the comparability context that constitution principle VI makes mandatory:
circuit, session type, weather, temperatures, difficulty and -- critically -- the
assist configuration. Assists change achievable lap times outright, so a progression
chart that ignores them will show a "breakthrough" that was really a settings change.

Marshal zones and weather forecast samples are skipped rather than decoded; they serve
no requirement in this feature and their bytes remain in the raw log (principle I).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import ScalarCodec
from f1dc.wire.f1_2023 import enums
from f1dc.wire.registry import register


@dataclass(frozen=True, slots=True)
class SessionData:
    weather: int
    track_temperature: int
    air_temperature: int
    total_laps: int
    track_length: int
    session_type: int
    track_id: int
    formula: int
    session_time_left: int
    session_duration: int
    pit_speed_limit: int
    game_paused: int
    is_spectating: int
    spectator_car_index: int
    sli_pro_native_support: int
    num_marshal_zones: int
    safety_car_status: int
    network_game: int
    num_weather_forecast_samples: int
    forecast_accuracy: int
    ai_difficulty: int
    season_link_identifier: int
    weekend_link_identifier: int
    session_link_identifier: int
    pit_stop_window_ideal_lap: int
    pit_stop_window_latest_lap: int
    pit_stop_rejoin_position: int
    steering_assist: int
    braking_assist: int
    gearbox_assist: int
    pit_assist: int
    pit_release_assist: int
    ers_assist: int
    drs_assist: int
    dynamic_racing_line: int
    dynamic_racing_line_type: int
    game_mode: int
    rule_set: int
    time_of_day: int
    session_length: int
    speed_units_lead_player: int
    temperature_units_lead_player: int
    speed_units_secondary_player: int
    temperature_units_secondary_player: int
    num_safety_car_periods: int
    num_virtual_safety_car_periods: int
    num_red_flag_periods: int

    @property
    def track_name(self) -> str:
        return enums.track_name(self.track_id)

    @property
    def session_type_name(self) -> str:
        return enums.session_type_name(self.session_type)

    @property
    def session_category(self) -> str:
        """Drives the lap-validity branch (FR-012)."""
        return enums.session_category(self.session_type)

    @property
    def weather_name(self) -> str:
        return enums.weather_name(self.weather)

    @property
    def assists(self) -> dict[str, int]:
        return {
            "steering": self.steering_assist,
            "braking": self.braking_assist,
            "gearbox": self.gearbox_assist,
            "pit": self.pit_assist,
            "pit_release": self.pit_release_assist,
            "ers": self.ers_assist,
            "drs": self.drs_assist,
            "racing_line": self.dynamic_racing_line,
            "racing_line_type": self.dynamic_racing_line_type,
        }

    @property
    def assists_summary(self) -> str:
        """Short human label for the library list."""
        on = [k for k, v in self.assists.items() if k != "racing_line_type" and v]
        # gearbox: 1 = manual, so it is only an assist when above 1
        if self.gearbox_assist <= 1 and "gearbox" in on:
            on.remove("gearbox")
        gearbox = "manual gearbox" if self.gearbox_assist <= 1 else "auto gearbox"
        return f"{'no assists' if not on else ', '.join(sorted(on))}, {gearbox}"


@register
class SessionCodec(ScalarCodec):
    packet_id = 1
    wire_size = 644
    name = "Session"

    BODY = struct.Struct(
        "<"
        "BbbBHBbBHHBBBBBB"  # weather .. numMarshalZones               (19 bytes)
        "105x"  # 21 marshal zones x 5 bytes -- not needed here
        "BBB"  # safetyCarStatus, networkGame, numWeatherForecastSamples
        "448x"  # 56 forecast samples x 8 bytes -- not needed here
        "BB"  # forecastAccuracy, aiDifficulty
        "III"  # season / weekend / session link identifiers
        "BBB"  # pit stop window ideal, latest, rejoin position
        "BBBBBBBBB"  # the nine assist settings
        "BB"  # gameMode, ruleSet
        "I"  # timeOfDay
        "BBBBBBBB"  # sessionLength .. numRedFlagPeriods
    )

    @classmethod
    def decode(cls, buf: bytes | memoryview) -> SessionData:
        return SessionData(*cls.unpack_body(buf))
