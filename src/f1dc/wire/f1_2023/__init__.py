"""F1 23 codecs (packet format 2023).

Importing this package registers every codec into
:data:`f1dc.wire.registry.default_registry` and, as a side effect, runs the wire-size
assertion on each one (T024). If any codec's declared fields stop summing to its
documented packet size, **import fails loudly here** rather than the software running on
silently wrong numbers.

The sizes asserted below were confirmed against a real capture: all thirteen packet types
arrived at exactly one size each, and every one matched the published specification.
"""

from __future__ import annotations

from f1dc.wire.f1_2023.car_damage import CarDamageCodec
from f1dc.wire.f1_2023.car_setups import CarSetupsCodec
from f1dc.wire.f1_2023.car_status import CarStatusCodec
from f1dc.wire.f1_2023.event import EventCodec
from f1dc.wire.f1_2023.final_classification import FinalClassificationCodec
from f1dc.wire.f1_2023.lap_data import LapDataCodec
from f1dc.wire.f1_2023.session import SessionCodec
from f1dc.wire.f1_2023.session_history import SessionHistoryCodec
from f1dc.wire.f1_2023.tyre_sets import TyreSetsCodec

PACKET_FORMAT = 2023

#: Every codec this build ships for the 2023 format.
CODECS = (
    SessionCodec,
    LapDataCodec,
    EventCodec,
    CarSetupsCodec,
    CarStatusCodec,
    FinalClassificationCodec,
    CarDamageCodec,
    SessionHistoryCodec,
    TyreSetsCodec,
)

#: Packet ids the game emits that this build deliberately does not decode (research R6).
#: Their bytes are preserved in the raw log, so a later feature can decode them from
#: recordings made today.
UNDECODED_PACKET_IDS = {
    0: "Motion (1349 bytes) -- racing line map, deferred",
    4: "Participants (1306 bytes) -- rival names, deferred",
    6: "CarTelemetry (1352 bytes) -- per-frame channels, deferred to feature 002",
    9: "LobbyInfo -- multiplayer lobbies, out of scope",
    13: "MotionEx (217 bytes) -- racing line map, deferred",
}

#: Wire sizes observed in the reference capture, keyed by packet id. Used by the contract
#: test to assert against reality rather than against this source file.
OBSERVED_WIRE_SIZES = {
    0: 1349,
    1: 644,
    2: 1131,
    3: 45,
    4: 1306,
    5: 1107,
    6: 1352,
    7: 1239,
    8: 1020,
    10: 953,
    11: 1460,
    12: 231,
    13: 217,
}

__all__ = [
    "CODECS",
    "OBSERVED_WIRE_SIZES",
    "PACKET_FORMAT",
    "UNDECODED_PACKET_IDS",
    "CarDamageCodec",
    "CarSetupsCodec",
    "CarStatusCodec",
    "EventCodec",
    "FinalClassificationCodec",
    "LapDataCodec",
    "SessionCodec",
    "SessionHistoryCodec",
    "TyreSetsCodec",
]
