"""T008-T011, T014 -- feature 003: per-lap car data, excursions, field, timeline, events.

Fed packet by packet by the sessionizer, then turned into the tables described in
specs/003-car-and-race-data/data-model.md. Rules measured on the reference race:

* **Energy counters reset at the line** (research R4): 2.58 MJ deployed just before a lap
  change, 0.00 just after. On the final lap they reset *after* the chequered flag, while
  the lap number holds. So per-lap deployed and harvested energy are each lap's MAXIMUM,
  since the counters only ever rise within a lap.
* **A tyre change mid-lap** (R5): tyre and brake aggregates use only samples taken while
  tyre age still equals the lap's starting age, so two sets are never averaged together.
* **Off-track** (R3): any wheel on rock, gravel, mud, sand or grass. Kerbs, concrete and
  the pit lane's metal surface are not. Runs closer than 5 m are merged.
* **The lap closes at the line**, as in traces: a lap clock reset after the lap is well
  under way ends it, so the cool-down lap after the flag is not counted into it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

WHEELS = ("fl", "fr", "rl", "rr")
OFF_TRACK = {3: "rock", 4: "gravel", 5: "mud", 6: "sand", 7: "grass"}
MERGE_GAP_M = 5.0
WRAP_CLOCK_MS = 2_000
WRAP_PREVIOUS_MS = 10_000
DAMAGE_PARTS = (
    "front_left_wing", "front_right_wing", "rear_wing", "floor",
    "diffuser", "sidepod", "gearbox", "engine",
)
#: Labelled only where a capture supports the meaning; anything else is shown as its codes.
#: Type 5 / infringement 27 on the reference race fall on exactly the laps (1 and 4) where
#: LapData's corner-cutting warning counter rose.
PENALTY_TYPES = {5: "Warning"}
INFRINGEMENTS = {27: "corner cutting"}

_DAMAGE_FIELDS = {part: f"{part}_damage" for part in DAMAGE_PARTS} | {"gearbox": "gear_box_damage"}


@dataclass
class _Lap:
    number: int
    tyre_age_start: int | None = None
    tyre_change: bool = False
    temps: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    engine_max: float = 0.0
    samples: int = 0
    drs_samples: int = 0
    ers_first: float | None = None
    ers_last: float | None = None
    deployed: float = 0.0
    harvested: float = 0.0
    ers_modes: set[int] = field(default_factory=set)
    fuel_first: float | None = None
    fuel_last: float | None = None
    fuel_mix: set[int] = field(default_factory=set)
    brake_bias: set[int] = field(default_factory=set)
    damage: dict[str, int] = field(default_factory=lambda: dict.fromkeys(DAMAGE_PARTS, 0))
    position: int | None = None
    gap_ahead_ms: int | None = None
    warnings: int = 0
    penalties: int = 0
    last_clock_ms: float = 0.0
    closed: bool = False


@dataclass
class _Excursion:
    lap: int
    start_m: float
    end_m: float
    session_time_s: float
    wheels: set[str]
    surfaces: set[str]


def _join(values: set[int]) -> str:
    return ",".join(str(v) for v in sorted(values))


class CarDataBuilder:
    """Accumulates feature-003 data for one session."""

    def __init__(self) -> None:
        self.laps: dict[int, _Lap] = {}
        self.current: _Lap | None = None
        self._distance = 0.0
        self._session_time = 0.0
        self._excursions: list[_Excursion] = []
        self._open: _Excursion | None = None
        self.participants: list = []
        self.history: dict[int, object] = {}
        self.classification: list = []
        self.timeline: list[dict] = []
        self.events: list[dict] = []
        self.tyre_sets = None

    # ------------------------------------------------------------------ feeding

    def on_lap_data(self, lap, session_time: float) -> None:
        number = lap.current_lap_num
        if number <= 0:
            return
        self._session_time = session_time
        record = self.laps.get(number)
        if record is None:
            self._close_excursion()
            record = self.laps[number] = _Lap(number)
            self.current = record
        if record.closed:
            return
        if (lap.current_lap_time_ms < WRAP_CLOCK_MS
                and record.last_clock_ms > WRAP_PREVIOUS_MS):
            # The line was crossed, but the game kept the lap number (chequered flag).
            record.closed = True
            self._close_excursion()
            return
        record.last_clock_ms = lap.current_lap_time_ms
        self._distance = lap.lap_distance
        record.position = lap.car_position or record.position
        # P1 has nobody ahead; an exact 0 ms is what the game reports in the pit lane.
        gap = lap.delta_to_car_in_front_ms
        record.gap_ahead_ms = None if lap.car_position == 1 or gap == 0 else gap
        record.warnings = max(record.warnings, lap.corner_cutting_warnings)
        record.penalties = max(record.penalties, lap.penalties)

    def _lap(self) -> _Lap | None:
        lap = self.current
        return None if lap is None or lap.closed else lap

    def on_status(self, status) -> None:
        lap = self._lap()
        if lap is None:
            return
        age = status.tyres_age_laps
        if lap.tyre_age_start is None:
            lap.tyre_age_start = age
        elif age < lap.tyre_age_start:
            lap.tyre_change = True
        energy = status.ers_store_energy / 1e6
        lap.ers_first = energy if lap.ers_first is None else lap.ers_first
        lap.ers_last = energy
        # Counters only rise within a lap, then reset: the maximum is the lap's total.
        lap.deployed = max(lap.deployed, status.ers_deployed_this_lap / 1e6)
        lap.harvested = max(
            lap.harvested,
            (status.ers_harvested_this_lap_mguk + status.ers_harvested_this_lap_mguh) / 1e6,
        )
        lap.ers_modes.add(status.ers_deploy_mode)
        lap.fuel_first = status.fuel_in_tank if lap.fuel_first is None else lap.fuel_first
        lap.fuel_last = status.fuel_in_tank
        lap.fuel_mix.add(status.fuel_mix)
        lap.brake_bias.add(status.front_brake_bias)

    def on_telemetry(self, t) -> None:
        lap = self._lap()
        if lap is None or self._distance < 0:
            return
        lap.samples += 1
        lap.drs_samples += 1 if t.drs else 0
        lap.engine_max = max(lap.engine_max, t.engine_temperature)
        if not lap.tyre_change:  # never mix two tyre sets (FR-005)
            for w in WHEELS:
                lap.temps[f"surface_{w}"].append(getattr(t, f"tyre_surface_temp_{w}"))
                lap.temps[f"inner_{w}"].append(getattr(t, f"tyre_inner_temp_{w}"))
                lap.temps[f"brake_{w}"].append(getattr(t, f"brake_temp_{w}"))
                lap.temps[f"pressure_{w}"].append(getattr(t, f"tyre_pressure_{w}"))
        self._track_excursion(lap.number, t)

    def on_damage(self, d) -> None:
        lap = self._lap()
        if lap is None:
            return
        for part, attr in _DAMAGE_FIELDS.items():
            lap.damage[part] = max(lap.damage[part], getattr(d, attr))

    def on_session(self, data, session_time: float) -> None:
        row = {
            "session_time_s": round(session_time, 1),
            "lap_number": self.current.number if self.current else 0,
            "weather": data.weather_name,
            "track_temp_c": data.track_temperature,
            "air_temp_c": data.air_temperature,
        }
        last = self.timeline[-1] if self.timeline else None
        if last is None or any(last[k] != row[k] for k in ("weather", "track_temp_c", "air_temp_c")):
            self.timeline.append(row)

    def on_event(self, event, session_time: float, player_index: int) -> None:
        if event.code not in ("FTLP", "OVTK", "SPTP", "PENA", "RTMT", "RCWN"):
            return
        detail = event.parsed()
        self.events.append({
            "session_time_s": round(session_time, 2),
            "lap_number": self.current.number if self.current else 0,
            "code": event.code,
            "vehicle_idx": detail.vehicle_idx,
            "other_vehicle_idx": detail.other_vehicle_idx,
            "value": detail.value,
            "involves_player": player_index in (detail.vehicle_idx, detail.other_vehicle_idx),
            "extra": detail.extra,
        })

    # ------------------------------------------------------------------ excursions

    def _track_excursion(self, lap_number: int, t) -> None:
        off = {w: OFF_TRACK[s] for w in WHEELS if (s := getattr(t, f"surface_type_{w}")) in OFF_TRACK}
        d = self._distance
        if off:
            if self._open and self._open.lap == lap_number and d - self._open.end_m <= MERGE_GAP_M:
                self._open.end_m = max(self._open.end_m, d)
                self._open.wheels |= set(off)
                self._open.surfaces |= set(off.values())
            else:
                self._close_excursion()
                self._open = _Excursion(lap_number, d, d, self._session_time, set(off), set(off.values()))
        elif self._open and d - self._open.end_m > MERGE_GAP_M:
            self._close_excursion()

    def _close_excursion(self) -> None:
        if self._open is not None:
            self._excursions.append(self._open)
            self._open = None

    # ------------------------------------------------------------------ output

    def lap_rows(self, session_uid: str) -> list[dict]:
        self._close_excursion()
        per_lap = defaultdict(list)
        for ex in self._excursions:
            per_lap[ex.lap].append(ex)

        rows, previous = [], None
        for number in sorted(self.laps):
            lap = self.laps[number]
            if lap.samples == 0 and lap.ers_first is None:
                continue
            row: dict = {"session_uid": session_uid, "lap_number": number}
            for w in WHEELS:
                for kind, label in (("surface", "tyre_surface"), ("inner", "tyre_inner"), ("brake", "brake")):
                    values = lap.temps.get(f"{kind}_{w}") or []
                    row[f"{label}_avg_{w}"] = sum(values) / len(values) if values else None
                    row[f"{label}_max_{w}"] = float(max(values)) if values else None
                pressures = lap.temps.get(f"pressure_{w}") or []
                row[f"pressure_avg_{w}"] = sum(pressures) / len(pressures) if pressures else None
            row["engine_temp_max"] = lap.engine_max or None
            row["tyre_change_in_lap"] = lap.tyre_change
            row["ers_start_mj"] = lap.ers_first
            row["ers_end_mj"] = lap.ers_last
            row["ers_deployed_mj"] = lap.deployed
            row["ers_harvested_mj"] = lap.harvested
            row["ers_balance_mj"] = lap.harvested - lap.deployed
            row["ers_modes"] = _join(lap.ers_modes)
            row["fuel_start_kg"] = lap.fuel_first
            row["fuel_end_kg"] = lap.fuel_last
            row["fuel_used_kg"] = (
                lap.fuel_first - lap.fuel_last
                if lap.fuel_first is not None and lap.fuel_last is not None else None
            )
            row["fuel_mix"] = _join(lap.fuel_mix)
            row["brake_bias"] = _join(lap.brake_bias)
            row["settings_changed"] = (previous is not None and any(
                row[k] != previous[k] for k in ("brake_bias", "ers_modes", "fuel_mix")
            )) or len(lap.brake_bias) > 1
            for part in DAMAGE_PARTS:
                row[f"damage_{part}"] = lap.damage[part]
            row["damage_increased"] = previous is not None and any(
                lap.damage[p] > previous[f"damage_{p}"] for p in DAMAGE_PARTS
            )
            excursions = per_lap.get(number, [])
            row["excursions"] = len(excursions)
            row["excursion_m"] = float(sum(e.end_m - e.start_m for e in excursions))
            row["drs_pct"] = 100.0 * lap.drs_samples / lap.samples if lap.samples else 0.0
            row["position_at_line"] = lap.position
            row["gap_ahead_ms_at_line"] = lap.gap_ahead_ms
            row["corner_warnings"] = lap.warnings
            row["penalties_s"] = lap.penalties
            rows.append(row)
            previous = row
        return rows

    def excursion_rows(self, session_uid: str) -> list[dict]:
        self._close_excursion()
        return [{
            "session_uid": session_uid,
            "lap_number": e.lap,
            "start_m": e.start_m,
            "length_m": max(0.0, e.end_m - e.start_m),
            "wheels": ",".join(w for w in WHEELS if w in e.wheels),
            "surface": ",".join(sorted(e.surfaces)),
            "session_time_s": e.session_time_s,
        } for e in self._excursions]

    # ------------------------------------------------------------------ the field

    def names(self) -> dict[int, str]:
        """Driver names, with a placeholder when the game withholds one (FR-019).

        Online, the game blanks the names of players who hide them; offline every car,
        AI included, carries its name.
        """
        return {
            idx: p.name.strip() or f"Driver #{p.race_number}"
            for idx, p in enumerate(self.participants)
        }

    def field_rows(
        self, session_uid: str, player_index: int, player_stints: list | None = None
    ) -> tuple[list[dict], list[dict]]:
        """The field. Rivals' stints are compounds and stop counts only.

        Their end laps are unusable: on the reference race the game reports the player's
        first stint ending on lap 2 (it ended on lap 4) and another car's ending on lap 0,
        identically in SessionHistory AND FinalClassification. Pit-stop counts and
        compounds are right in both, so that is what is shown. The player's own stints
        come from feature 001's tyre-age evidence instead.
        """
        from f1dc.wire.f1_2023 import enums  # local: only needed at output time

        names = self.names()
        cars, laps = [], []
        for idx, history in sorted(self.history.items()):
            recorded = [(i + 1, h) for i, h in enumerate(history.laps) if h.is_recorded]
            best = min(recorded, key=lambda x: x[1].lap_time_ms) if recorded else None
            final = self.classification[idx] if idx < len(self.classification) else None
            participant = self.participants[idx] if idx < len(self.participants) else None
            if idx == player_index and player_stints:
                stints = [
                    f"{s.tyre_visual_compound_name} {s.start_lap}-{s.end_lap or '…'}"
                    for s in player_stints
                ]
            else:
                compounds = " → ".join(s.visual_compound_name for s in history.stints)
                stops = final.num_pit_stops if final else max(0, len(history.stints) - 1)
                stints = [f"{compounds} ({stops} stop{'s' if stops != 1 else ''})"]
            cars.append({
                "session_uid": session_uid,
                "car_idx": idx,
                "name": names.get(idx, f"Car {idx}"),
                "team_id": participant.team_id if participant else None,
                "race_number": participant.race_number if participant else None,
                "ai_controlled": bool(participant.ai_controlled) if participant else None,
                "is_player": idx == player_index,
                "best_lap_ms": best[1].lap_time_ms if best else None,
                "best_lap_number": best[0] if best else None,
                "num_laps": len(recorded),
                "finish_position": final.position if final else None,
                "result_status": enums.result_status_name(final.result_status) if final else None,
                "stints": " · ".join(stints),
            })
            for number, h in recorded:
                laps.append({
                    "session_uid": session_uid, "car_idx": idx, "lap_number": number,
                    "lap_time_ms": h.lap_time_ms, "valid": h.is_valid,
                })
        return cars, laps

    # ------------------------------------------------------------------ timeline etc.

    def event_rows(self, session_uid: str) -> list[dict]:
        names = self.names()

        def who(idx):
            return names.get(idx, f"Car {idx}") if idx is not None else "?"

        rows = []
        for e in self.events:
            code, value = e["code"], e["value"]
            if code == "OVTK":
                text = f"{who(e['vehicle_idx'])} overtook {who(e['other_vehicle_idx'])}"
            elif code == "FTLP":
                text = f"Fastest lap: {who(e['vehicle_idx'])} {value:.3f} s"
            elif code == "SPTP":
                text = f"Speed trap: {who(e['vehicle_idx'])} {value:.1f} km/h"
            elif code == "PENA":
                kind = PENALTY_TYPES.get(e["extra"].get("penalty_type"))
                cause = INFRINGEMENTS.get(e["extra"].get("infringement_type"))
                text = (f"{kind or 'Penalty'}: {who(e['vehicle_idx'])}"
                        + (f" -- {cause}" if cause else
                           f" (type {e['extra'].get('penalty_type')}, "
                           f"infringement {e['extra'].get('infringement_type')})"))
            elif code == "RTMT":
                text = f"Retired: {who(e['vehicle_idx'])}"
            else:
                text = f"Race winner: {who(e['vehicle_idx'])}"
            rows.append({
                "session_uid": session_uid,
                "session_time_s": e["session_time_s"],
                "lap_number": e["lap_number"],
                "code": code,
                "vehicle_idx": e["vehicle_idx"],
                "other_vehicle_idx": e["other_vehicle_idx"],
                "value": None if value is None or (isinstance(value, float) and math.isnan(value)) else value,
                "involves_player": e["involves_player"],
                "description": text,
            })
        return rows

    def timeline_rows(self, session_uid: str) -> list[dict]:
        return [{"session_uid": session_uid, **row} for row in self.timeline]

    def tyre_set_rows(self, session_uid: str) -> list[dict]:
        if self.tyre_sets is None:
            return []
        return [{
            "session_uid": session_uid,
            "set_index": i,
            "actual_compound": s.actual_compound_name,
            "visual_compound": s.visual_compound_name,
            "wear_pct": s.wear,
            "available": s.is_available,
            "fitted": s.is_fitted,
            "lap_delta_ms": s.lap_delta_time_ms,
            "life_span": s.life_span,
            "usable_life": s.usable_life,
        } for i, s in enumerate(self.tyre_sets.sets)]
