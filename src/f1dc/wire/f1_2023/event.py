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
