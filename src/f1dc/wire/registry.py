"""T013 -- parser dispatch keyed on the wire contract.

Constitution principle III: every parser is selected by
``(packetFormat, packetId, packetVersion)`` read from the packet header. Assuming the
2023 format is forbidden, and an unrecognised tuple is counted and reported rather than
coerced into a neighbouring parser (FR-017).

This is what keeps F1 24/25/26 support additive instead of a rewrite, and what stops a
future game patch from silently corrupting historical analysis.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from f1dc.wire.base import PacketCodec

DispatchKey = tuple[int, int, int]


class DuplicateCodecError(Exception):
    """Two codecs claim the same dispatch key."""


@dataclass
class Registry:
    """Maps wire contracts to codecs, and remembers what it could not decode."""

    _codecs: dict[DispatchKey, type[PacketCodec]] = field(default_factory=dict)
    unknown: Counter[DispatchKey] = field(default_factory=Counter)

    def register(self, codec: type[PacketCodec]) -> type[PacketCodec]:
        """Register a codec for every version it declares. Usable as a decorator."""
        for key in codec.dispatch_keys():
            if key in self._codecs and self._codecs[key] is not codec:
                raise DuplicateCodecError(
                    f"{key} already registered to {self._codecs[key].__name__}, "
                    f"cannot also register {codec.__name__}"
                )
            self._codecs[key] = codec
        return codec

    def get(self, key: DispatchKey) -> type[PacketCodec] | None:
        """Return the codec for *key*, or None -- recording the miss.

        Returning None rather than raising is deliberate: one unknown packet type must
        not abort ingest of an otherwise readable session (spec edge case, "a recording
        contains information the app cannot yet interpret").
        """
        codec = self._codecs.get(key)
        if codec is None:
            self.unknown[key] += 1
        return codec

    def known_keys(self) -> list[DispatchKey]:
        return sorted(self._codecs)

    def known_formats(self) -> set[int]:
        return {k[0] for k in self._codecs}

    def unknown_report(self) -> list[str]:
        """Human-readable description of everything that could not be dispatched."""
        lines = []
        for (fmt, pid, ver), count in sorted(self.unknown.items()):
            if fmt not in self.known_formats():
                why = f"packet format {fmt} is not supported (this build knows {sorted(self.known_formats())})"
            else:
                why = f"no codec for packet id {pid} version {ver} in format {fmt}"
            lines.append(f"{count} packet(s): {why}")
        return lines

    @property
    def unknown_count(self) -> int:
        return sum(self.unknown.values())

    def reset_unknown(self) -> None:
        self.unknown.clear()


#: The registry the shipped codecs register into.
default_registry = Registry()


def register(codec: type[PacketCodec]) -> type[PacketCodec]:
    """Decorator registering a codec into :data:`default_registry`."""
    return default_registry.register(codec)
