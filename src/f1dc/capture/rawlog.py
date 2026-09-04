"""T008 -- raw log framing, per contracts/raw-log-format.md.

The raw log is the one artifact that cannot be regenerated, so the format is the
simplest thing that preserves everything and can be written without parsing:
a 16-byte file header, then length-prefixed timestamped datagrams.

Standard library only (constitution principle II) -- this module is imported by the
recorder, which runs in the capture path.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

MAGIC = b"F1DCRAW\x00"
FORMAT_VERSION = 1

FILE_HEADER = struct.Struct("<8sHHI")  # magic, version, port, reserved
RECORD_HEADER = struct.Struct("<Id")  # datagram length, monotonic receive timestamp

assert FILE_HEADER.size == 16, FILE_HEADER.size
assert RECORD_HEADER.size == 12, RECORD_HEADER.size

#: Largest datagram the game can send is Motion at 1349 bytes; this bound exists to
#: reject a corrupt length field rather than to allocate hundreds of megabytes.
MAX_DATAGRAM = 65535


class RawLogError(Exception):
    """The file is not a readable raw log."""


@dataclass(frozen=True, slots=True)
class Record:
    """One captured datagram."""

    timestamp: float
    """Monotonic seconds since capture start."""

    payload: bytes


class RawLogWriter:
    """Append-only writer. Never seeks backwards.

    The writer performs no parsing, no filtering and no compression. Every datagram
    received is written, including packet types we cannot decode, malformed datagrams,
    and ``sessionUID == 0`` menu traffic -- filtering is ingest's job.
    """

    def __init__(self, path: Path, port: int) -> None:
        self.path = path
        self.port = port
        self._fh: BinaryIO | None = None
        self.records_written = 0
        self.bytes_written = 0

    def __enter__(self) -> RawLogWriter:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("wb", buffering=1024 * 1024)
        self._fh.write(FILE_HEADER.pack(MAGIC, FORMAT_VERSION, self.port, 0))

    def write(self, payload: bytes, timestamp: float) -> None:
        if self._fh is None:
            raise RawLogError("writer is not open")
        self._fh.write(RECORD_HEADER.pack(len(payload), timestamp))
        self._fh.write(payload)
        self.records_written += 1
        self.bytes_written += len(payload)

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None


def read_file_header(fh: BinaryIO) -> tuple[int, int]:
    """Return ``(format_version, port)``, raising if this is not a raw log."""
    blob = fh.read(FILE_HEADER.size)
    if len(blob) < FILE_HEADER.size:
        raise RawLogError("file is shorter than the raw log header")
    magic, version, port, _reserved = FILE_HEADER.unpack(blob)
    if magic != MAGIC:
        raise RawLogError(f"bad magic {magic!r}; not an f1raw file")
    if version != FORMAT_VERSION:
        raise RawLogError(f"unsupported raw log format version {version}")
    return version, port


def iter_records(source: Path | BinaryIO) -> Iterator[Record]:
    """Yield every complete record.

    A truncated file -- an interrupted capture, or one still being written -- is read
    up to its last complete record and then stops cleanly. This is what makes an
    interrupted session usable rather than lost (spec edge case).
    """
    opened = False
    if isinstance(source, Path):
        fh: BinaryIO = source.open("rb", buffering=1024 * 1024)
        opened = True
    else:
        fh = source

    try:
        read_file_header(fh)
        while True:
            head = fh.read(RECORD_HEADER.size)
            if len(head) < RECORD_HEADER.size:
                return  # clean end, or truncated mid-header
            length, timestamp = RECORD_HEADER.unpack(head)
            if length > MAX_DATAGRAM:
                raise RawLogError(f"implausible datagram length {length}; file is corrupt")
            payload = fh.read(length)
            if len(payload) < length:
                return  # truncated mid-payload
            yield Record(timestamp=timestamp, payload=payload)
    finally:
        if opened:
            fh.close()
