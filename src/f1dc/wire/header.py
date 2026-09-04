"""T011 -- the 29-byte packet header shared by every F1 23 telemetry packet.

Little-endian, packed, no alignment padding. Validated against real captured bytes:
all 13 packet types in the reference capture decoded with consistent field values.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER = struct.Struct("<HBBBBBQfIIBB")
HEADER_SIZE = HEADER.size

assert HEADER_SIZE == 29, HEADER_SIZE

#: Maximum cars in any per-car array, in every packet, in every supported format.
MAX_CARS = 22


@dataclass(frozen=True, slots=True)
class PacketHeader:
    packet_format: int
    """2023 for F1 23. Parser dispatch keys on this (constitution principle III)."""

    game_year: int
    game_major_version: int
    game_minor_version: int
    packet_version: int
    packet_id: int
    session_uid: int
    """Zero means menu state and is discarded by ingest (FR-007)."""

    session_time: float
    frame_identifier: int
    """Resets on a flashback."""

    overall_frame_identifier: int
    """Does NOT reset on a flashback. Divergence from frame_identifier is an exact
    flashback signal requiring no heuristics."""

    player_car_index: int
    secondary_player_car_index: int

    @property
    def is_menu_state(self) -> bool:
        return self.session_uid == 0

    @property
    def has_frame_counter(self) -> bool:
        """False for end-of-session packets, which carry frame identifiers of zero.

        Discovered against the reference capture: the Event, SessionHistory and
        FinalClassification packets sent as a session closes all report
        ``frame_identifier == 0`` and ``overall_frame_identifier == 0`` despite arriving
        at ``session_time`` ~391 s, well after frame 42 511.

        This matters directly: the packet-loss metric counts gaps in frame identifiers,
        so treating these as real frames would report a phantom 42 000-frame loss at the
        end of every session.
        """
        return not (self.frame_identifier == 0 and self.overall_frame_identifier == 0)

    @property
    def game_version(self) -> str:
        return f"{self.game_major_version}.{self.game_minor_version:02d}"

    @property
    def dispatch_key(self) -> tuple[int, int, int]:
        """The tuple every parser is selected by (constitution principle III)."""
        return (self.packet_format, self.packet_id, self.packet_version)


def decode_header(buf: bytes | memoryview, offset: int = 0) -> PacketHeader:
    """Decode the packet header. Raises ``struct.error`` if the buffer is too short."""
    return PacketHeader(*HEADER.unpack_from(buf, offset))


def peek_dispatch(buf: bytes | memoryview) -> tuple[int, int, int] | None:
    """Cheaply read ``(packet_format, packet_id, packet_version)`` without full decode.

    Returns ``None`` when the buffer is too short to be a packet at all.
    """
    if len(buf) < HEADER_SIZE:
        return None
    packet_format = int.from_bytes(buf[0:2], "little")
    packet_version = buf[5]
    packet_id = buf[6]
    return (packet_format, packet_id, packet_version)
