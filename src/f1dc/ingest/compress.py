"""T056 -- compression, deliberately outside the capture path.

Constitution principle II forbids compression in the recorder, and ``zstandard`` is a
third-party dependency with no business in the process that must not fail. So raw logs
are written uncompressed and squeezed here, after the session has closed.

The original is removed only after the compressed file has been read back and verified.
Losing a raw log to a bad compression run would be losing the one artifact that cannot be
regenerated.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

import zstandard

COMPRESSION_LEVEL = 10
ZST_SUFFIX = ".zst"


def is_compressed(path: Path) -> bool:
    return path.name.endswith(ZST_SUFFIX)


@contextlib.contextmanager
def open_raw(path: Path) -> Iterator[BinaryIO]:
    """Open a raw log for reading, transparently decompressing a ``.zst``."""
    if not is_compressed(path):
        with path.open("rb", buffering=1 << 20) as handle:
            yield handle
        return

    decompressor = zstandard.ZstdDecompressor()
    with path.open("rb") as compressed:
        with decompressor.stream_reader(compressed) as reader:
            yield reader  # type: ignore[misc]


def compress_log(
    path: Path, *, level: int = COMPRESSION_LEVEL, remove_original: bool = True
) -> Path:
    """Compress a raw log, verify it, then optionally remove the original.

    Returns the compressed path. If the file is already compressed it is returned as-is.
    """
    if is_compressed(path):
        return path

    destination = path.with_name(path.name + ZST_SUFFIX)
    compressor = zstandard.ZstdCompressor(level=level)

    with path.open("rb") as source, destination.open("wb") as target:
        compressor.copy_stream(source, target, read_size=1 << 20, write_size=1 << 20)

    if not _verify(path, destination):
        destination.unlink(missing_ok=True)
        raise OSError(f"compressed copy of {path.name} did not verify; original kept")

    if remove_original:
        path.unlink(missing_ok=True)
    return destination


def _verify(original: Path, compressed: Path) -> bool:
    """Decompress and compare byte counts before we delete anything irreplaceable."""
    expected = original.stat().st_size
    seen = 0
    try:
        with open_raw(compressed) as handle:
            while chunk := handle.read(1 << 20):
                seen += len(chunk)
    except (OSError, zstandard.ZstdError):
        return False
    return seen == expected


def compressed_ratio(original_bytes: int, compressed_bytes: int) -> float:
    if compressed_bytes <= 0:
        return 0.0
    return original_bytes / compressed_bytes
