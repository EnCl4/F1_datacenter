"""Codec base classes, and T024 -- the import-time wire-size assertion.

Constitution principle IV: a parser is not correct because a document says so. Every
codec declares the wire size the specification states, and this module refuses to let
the process start if a codec's declared fields do not sum to it.

That check caught nothing at import during development only because the sizes were
verified against a real capture first -- all 13 packet types arrived at exactly one
size each. The assertion exists so a future edit cannot quietly break that.
"""

from __future__ import annotations

import struct
from typing import ClassVar

from f1dc.wire.header import HEADER_SIZE, MAX_CARS


class WireSizeError(Exception):
    """A codec's fields do not sum to its declared wire size."""


class PacketCodec:
    """Base for all packet codecs.

    Subclasses declare ``packet_id`` and ``wire_size`` and implement ``computed_size``.
    Declare ``abstract=True`` in the class definition to skip the size check for
    intermediate base classes.
    """

    packet_format: ClassVar[int] = 2023
    packet_id: ClassVar[int]
    packet_versions: ClassVar[tuple[int, ...]] = (1,)
    wire_size: ClassVar[int]
    name: ClassVar[str] = "unnamed"
    abstract: ClassVar[bool] = True

    def __init_subclass__(cls, abstract: bool = False, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.abstract = abstract
        if abstract:
            return

        for required in ("packet_id", "wire_size"):
            if not hasattr(cls, required):
                raise WireSizeError(f"{cls.__name__} does not declare {required}")

        computed = cls.computed_size()
        if computed != cls.wire_size:
            raise WireSizeError(
                f"{cls.__name__}: declared fields sum to {computed} bytes but the "
                f"{cls.packet_format} specification says {cls.wire_size}. "
                f"A mismatch here means every value this codec produces is wrong."
            )

    @classmethod
    def computed_size(cls) -> int:
        raise NotImplementedError

    @classmethod
    def dispatch_keys(cls) -> list[tuple[int, int, int]]:
        return [(cls.packet_format, cls.packet_id, v) for v in cls.packet_versions]


class ScalarCodec(PacketCodec, abstract=True):
    """A packet whose body is one fixed structure (no per-car array)."""

    BODY: ClassVar[struct.Struct]

    @classmethod
    def computed_size(cls) -> int:
        return HEADER_SIZE + cls.BODY.size

    @classmethod
    def unpack_body(cls, buf: bytes | memoryview) -> tuple:
        return cls.BODY.unpack_from(buf, HEADER_SIZE)


class PerCarCodec(PacketCodec, abstract=True):
    """A packet carrying a fixed 22-element array of per-car structures.

    Feature 001 records the player's car only, so ``unpack_car`` with the header's
    ``player_car_index`` is the common path -- but the array is always present in full,
    which is why "player only" is a decision about the derived store and not about what
    the raw log contains.
    """

    PREFIX: ClassVar[struct.Struct | None] = None
    """Fields between the header and the array, e.g. FinalClassification's numCars."""

    ITEM: ClassVar[struct.Struct]
    ITEM_COUNT: ClassVar[int] = MAX_CARS
    """Usually 22 cars, but TyreSets carries 20 tyre sets for a single car."""

    TRAILER: ClassVar[struct.Struct | None] = None
    """Fields after the array, e.g. CarTelemetry's suggested gear."""

    @classmethod
    def _array_offset(cls) -> int:
        return HEADER_SIZE + (cls.PREFIX.size if cls.PREFIX is not None else 0)

    @classmethod
    def computed_size(cls) -> int:
        total = cls._array_offset() + cls.ITEM.size * cls.ITEM_COUNT
        if cls.TRAILER is not None:
            total += cls.TRAILER.size
        return total

    @classmethod
    def unpack_prefix(cls, buf: bytes | memoryview) -> tuple:
        if cls.PREFIX is None:
            return ()
        return cls.PREFIX.unpack_from(buf, HEADER_SIZE)

    @classmethod
    def unpack_car(cls, buf: bytes | memoryview, index: int) -> tuple:
        if not 0 <= index < cls.ITEM_COUNT:
            raise IndexError(f"index {index} out of range for {cls.__name__}")
        return cls.ITEM.unpack_from(buf, cls._array_offset() + index * cls.ITEM.size)

    @classmethod
    def unpack_all_cars(cls, buf: bytes | memoryview) -> list[tuple]:
        return [cls.unpack_car(buf, i) for i in range(cls.ITEM_COUNT)]

    @classmethod
    def unpack_trailer(cls, buf: bytes | memoryview) -> tuple:
        if cls.TRAILER is None:
            return ()
        offset = cls._array_offset() + cls.ITEM.size * cls.ITEM_COUNT
        return cls.TRAILER.unpack_from(buf, offset)
