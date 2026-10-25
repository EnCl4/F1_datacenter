"""T002 -- PacketParticipantsData, 1306 bytes.

Sent once per second. It names every car on the grid: the driver, the team, the race
number and whether a human or the AI drives it. Its header is followed by ``numActiveCars``
and then 22 fixed 58-byte participant entries; only the first ``numActiveCars`` are live.

Verified against a real capture: the packet is 1306 bytes, the names decode, and the
player's car (index 19) is VERSTAPPEN, not AI-controlled.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.registry import register


@dataclass(frozen=True, slots=True)
class ParticipantData:
    ai_controlled: int
    driver_id: int
    network_id: int
    team_id: int
    my_team: int
    race_number: int
    nationality: int
    name: str
    your_telemetry: int
    show_online_names: int
    platform: int


@register
class ParticipantsCodec(PerCarCodec):
    packet_id = 4
    wire_size = 1306
    name = "Participants"

    PREFIX = struct.Struct("<B")  # numActiveCars
    ITEM = struct.Struct(
        "<"
        "7B"  # aiControlled, driverId, networkId, teamId, myTeam, raceNumber, nationality
        "48s"  # name, NUL-terminated UTF-8 in a fixed field
        "3B"  # yourTelemetry, showOnlineNames, platform
    )

    @classmethod
    def num_active(cls, buf: bytes | memoryview) -> int:
        return cls.unpack_prefix(buf)[0]

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> ParticipantData:
        v = cls.unpack_car(buf, index)
        raw_name = v[7].split(b"\x00", 1)[0]
        return ParticipantData(
            *v[:7],
            raw_name.decode("utf-8", errors="replace"),
            v[8],
            v[9],
            v[10],
        )

    @classmethod
    def decode_active(cls, buf: bytes | memoryview) -> list[ParticipantData]:
        """Only the cars the packet says are active."""
        return [cls.decode_car(buf, i) for i in range(min(cls.num_active(buf), cls.ITEM_COUNT))]
