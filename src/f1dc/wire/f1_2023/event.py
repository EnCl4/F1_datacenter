"""T023 -- PacketEventData, 45 bytes.

Only the four-character event code is decoded. The 12-byte detail payload is a union
whose interpretation depends on the code, and nothing in feature 001 needs it -- session
end detection needs the code alone.

Those 12 bytes are preserved verbatim in the raw log regardless (constitution principle
I), so a later feature can decode penalties, overtakes and speed traps from recordings
made today without re-driving anything. It is exposed here as ``detail`` so that work
needs no format change.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import ScalarCodec
from f1dc.wire.f1_2023 import enums
from f1dc.wire.registry import register

_NONE_BYTE = 255

_FTLP = struct.Struct("<Bf")  # vehicleIdx, lapTime (s)
_OVTK = struct.Struct("<BB")  # overtakingVehicleIdx, beingOvertakenVehicleIdx
_SPTP = struct.Struct("<BfBBBf")  # vehicleIdx, speed, overall, driver, fastestIdx, fastest
_PENA = struct.Struct("<7B")  # penaltyType, infringementType, vehicle, other, time, lap, places
_SINGLE_VEHICLE = struct.Struct("<B")  # RTMT, RCWN


@dataclass(frozen=True, slots=True)
class EventDetail:
    vehicle_idx: int | None
    other_vehicle_idx: int | None
    value: float | None
    extra: dict


@dataclass(frozen=True, slots=True)
class EventData:
    code: str
    detail: bytes
    """Undecoded 12-byte union. Meaning depends on `code`; deferred (research R6)."""

    @property
    def description(self) -> str:
        return enums.event_description(self.code)

    @property
    def is_session_end(self) -> bool:
        """True for SEND and CHQF -- the session reached its natural end (FR-014)."""
        return self.code in enums.SESSION_END_EVENTS

    @property
    def is_flashback(self) -> bool:
        return self.code == "FLBK"

    def parsed(self) -> EventDetail:
        """Decode the 12-byte ``detail`` union according to ``code``."""
        d = self.detail
        if self.code == "FTLP":
            vehicle, lap_time = _FTLP.unpack_from(d)
            return EventDetail(vehicle, None, lap_time, {})
        if self.code == "OVTK":
            overtaking, overtaken = _OVTK.unpack_from(d)
            return EventDetail(overtaking, overtaken, None, {})
        if self.code == "SPTP":
            vehicle, speed, overall, driver, fastest_idx, fastest_speed = _SPTP.unpack_from(d)
            return EventDetail(
                vehicle,
                None,
                speed,
                {
                    "is_overall_fastest": bool(overall),
                    "is_driver_fastest": bool(driver),
                    "fastest_vehicle_idx": fastest_idx,
                    "fastest_speed": fastest_speed,
                },
            )
        if self.code == "PENA":
            penalty, infringement, vehicle, other, time, lap_num, places = _PENA.unpack_from(d)
            return EventDetail(
                vehicle,
                None if other == _NONE_BYTE else other,
                None if time == _NONE_BYTE else float(time),
                {
                    "penalty_type": penalty,
                    "infringement_type": infringement,
                    "time": time,
                    "lap_num": lap_num,
                    "places_gained": places,
                },
            )
        if self.code in ("RTMT", "RCWN"):
            (vehicle,) = _SINGLE_VEHICLE.unpack_from(d)
            return EventDetail(vehicle, None, None, {})
        return EventDetail(None, None, None, {})


@register
class EventCodec(ScalarCodec):
    packet_id = 3
    wire_size = 45
    name = "Event"

    BODY = struct.Struct("<4s12s")

    @classmethod
    def decode(cls, buf: bytes | memoryview) -> EventData:
        raw_code, detail = cls.unpack_body(buf)
        return EventData(code=raw_code.decode("ascii", errors="replace"), detail=detail)
