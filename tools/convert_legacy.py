"""Convert a probe_udp.py capture into the proper .f1raw format.

The original probe wrote bare length-prefixed records with no file header. The raw log
format adds a 16-byte header carrying magic, format version and the listening port, which
is what lets a reader confirm a file is what it claims to be.

Records are copied byte-for-byte -- the datagrams themselves are untouched, so nothing is
lost or reinterpreted. The original file is left in place.

Usage:
    python tools/convert_legacy.py C:/F1Data/raw/calibration.bin
    python tools/convert_legacy.py C:/F1Data/raw/calibration.bin --out custom.f1raw
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f1dc.capture.rawlog import RECORD_HEADER, RawLogWriter  # noqa: E402
from f1dc.wire.header import HEADER_SIZE, decode_header  # noqa: E402


def read_legacy(path: Path):
    with path.open("rb", buffering=1 << 20) as fh:
        while True:
            head = fh.read(RECORD_HEADER.size)
            if len(head) < RECORD_HEADER.size:
                return
            length, timestamp = RECORD_HEADER.unpack(head)
            payload = fh.read(length)
            if len(payload) < length:
                return  # truncated capture: keep what we have
            yield timestamp, payload


def default_output(source: Path) -> Path:
    """Name the output the way the recorder would have, so ingest can date it."""
    captured = datetime.fromtimestamp(source.stat().st_mtime, tz=UTC)
    stamp = captured.strftime("%Y-%m-%dT%H-%M-%S")

    session_uid = 0
    for _ts, payload in read_legacy(source):
        if len(payload) >= HEADER_SIZE:
            header = decode_header(payload)
            if header.session_uid:
                session_uid = header.session_uid
                break
    return source.with_name(f"{stamp}_{session_uid}.f1raw")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--port", type=int, default=20777)
    args = ap.parse_args()

    if not args.source.exists():
        print(f"no such file: {args.source}", file=sys.stderr)
        return 1

    destination = args.out or default_output(args.source)
    if destination.exists():
        print(f"{destination.name} already exists; nothing to do")
        return 0

    seen: Counter[int] = Counter()
    writer = RawLogWriter(destination, args.port)
    writer.open()
    try:
        for timestamp, payload in read_legacy(args.source):
            writer.write(payload, timestamp)
            if len(payload) >= HEADER_SIZE:
                seen[decode_header(payload).packet_id] += 1
    finally:
        writer.close()

    print(f"converted {args.source.name} -> {destination.name}")
    print(f"  {writer.records_written} records, {writer.bytes_written / 1e6:.1f} MB of datagrams")
    print(f"  packet ids: {dict(sorted(seen.items()))}")
    print(f"\noriginal left in place at {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
