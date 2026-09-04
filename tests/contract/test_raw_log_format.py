"""T009 -- raw log framing contract.

The raw log is the only artifact that cannot be regenerated, so its guarantees are
tested directly: round-trip fidelity, and readability of a truncated file.

That second property is what makes an interrupted capture usable rather than lost --
a crashed game, a power cut, or a file still being written.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from f1dc.capture.rawlog import (
    FILE_HEADER,
    FORMAT_VERSION,
    MAGIC,
    RawLogError,
    RawLogWriter,
    iter_records,
    read_file_header,
)


def test_header_and_record_sizes_are_fixed() -> None:
    """These sizes are the contract; changing them is a format version bump."""
    assert FILE_HEADER.size == 16
    assert MAGIC == b"F1DCRAW\x00"
    assert FORMAT_VERSION == 1


def test_round_trip_preserves_bytes_exactly(tmp_path: Path) -> None:
    payloads = [b"", b"\x00", b"hello", bytes(range(256)), b"\xff" * 1349]
    path = tmp_path / "rt.f1raw"

    with RawLogWriter(path, port=20777) as w:
        for i, p in enumerate(payloads):
            w.write(p, timestamp=i * 0.5)

    out = list(iter_records(path))
    assert [r.payload for r in out] == payloads
    assert [r.timestamp for r in out] == [0.0, 0.5, 1.0, 1.5, 2.0]


def test_port_is_recorded_in_the_file_header(tmp_path: Path) -> None:
    path = tmp_path / "port.f1raw"
    with RawLogWriter(path, port=20777) as w:
        w.write(b"x", 0.0)
    with path.open("rb") as fh:
        version, port = read_file_header(fh)
    assert (version, port) == (FORMAT_VERSION, 20777)


@pytest.mark.parametrize("cut", [1, 5, 12, 13, 20])
def test_truncated_file_reads_up_to_last_complete_record(tmp_path: Path, cut: int) -> None:
    """An interrupted capture must remain usable, not raise."""
    path = tmp_path / "trunc.f1raw"
    with RawLogWriter(path, port=20777) as w:
        w.write(b"first-record", 1.0)
        w.write(b"second-record", 2.0)

    full = path.read_bytes()
    path.write_bytes(full[:-cut])

    out = list(iter_records(path))
    assert [r.payload for r in out] == [b"first-record"]


def test_rejects_a_file_that_is_not_a_raw_log(tmp_path: Path) -> None:
    path = tmp_path / "bogus.f1raw"
    path.write_bytes(b"not an f1raw file at all, really")
    with pytest.raises(RawLogError, match="bad magic"):
        list(iter_records(path))


def test_rejects_an_unsupported_format_version(tmp_path: Path) -> None:
    path = tmp_path / "future.f1raw"
    path.write_bytes(FILE_HEADER.pack(MAGIC, 99, 20777, 0))
    with pytest.raises(RawLogError, match="unsupported raw log format version"):
        list(iter_records(path))


def test_rejects_an_implausible_length_rather_than_allocating(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.f1raw"
    with path.open("wb") as fh:
        fh.write(FILE_HEADER.pack(MAGIC, FORMAT_VERSION, 20777, 0))
        fh.write(struct.pack("<Id", 4_000_000_000, 0.0))
    with pytest.raises(RawLogError, match="implausible datagram length"):
        list(iter_records(path))


def test_the_committed_fixture_is_a_valid_raw_log(fixture_path: Path) -> None:
    with fixture_path.open("rb") as fh:
        version, port = read_file_header(fh)
    assert version == FORMAT_VERSION
    assert port == 20777


def test_fixture_stays_within_its_size_budget(fixture_path: Path) -> None:
    """It has to remain committable; principle VIII is about data, not test assets."""
    size = fixture_path.stat().st_size
    assert size < 5 * 1024 * 1024, f"fixture grew to {size / 1e6:.1f} MB"
