"""T010 -- build the committed test fixture from a full capture.

Constitution principle IV requires every parser to be tested against real captured bytes,
but a 229 MB capture cannot live in git. This builds a curated slice that keeps what the
tests need and drops what they do not.

The subsampling is **event-preserving, not time-based**: every packet in which something
meaningful changed is kept in full -- a lap transition, entering or leaving the pits, a
lap being invalidated, a tyre compound change. Periodic samples fill the gaps. That way
lap-splitting tests still see exact transitions rather than an interpolation of them.

Usage:
    python tools/build_fixture.py <source.bin> <dest.f1raw> [--legacy-probe]

``--legacy-probe`` reads the original probe_udp.py framing, which had no file header.
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f1dc.capture.rawlog import RECORD_HEADER, RawLogWriter  # noqa: E402
from f1dc.wire.header import HEADER_SIZE, decode_header  # noqa: E402

# Periodic sampling intervals in seconds, by packet id. Anything not listed keeps a small
# fixed number of packets, purely so its codec has real bytes to decode.
SAMPLE_INTERVAL = {
    1: 1.0,  # Session
    2: 0.2,  # LapData -- densest, since lap splitting depends on it
    5: 10.0,  # CarSetups
    7: 1.0,  # CarStatus
    10: 1.0,  # CarDamage
    11: 5.0,  # SessionHistory (cumulative, so sparse sampling loses nothing)
    12: 10.0,  # TyreSets
}
KEEP_ALL = {3, 8}  # Event, FinalClassification
CODEC_SAMPLE_COUNT = 20  # Motion, Participants, CarTelemetry, MotionEx


def read_legacy(path: Path):
    """Read the original probe_udp.py format: bare records, no file header."""
    with path.open("rb", buffering=1 << 20) as fh:
        while True:
            head = fh.read(RECORD_HEADER.size)
            if len(head) < RECORD_HEADER.size:
                return
            length, ts = RECORD_HEADER.unpack(head)
            payload = fh.read(length)
            if len(payload) < length:
                return
            yield ts, payload


def lap_state(buf: bytes) -> tuple | None:
    """Player lap fields whose change must never be lost by subsampling."""
    hdr = decode_header(buf)
    off = HEADER_SIZE + hdr.player_car_index * 50
    try:
        # currentLapNum(+31), pitStatus(+32), currentLapInvalid(+35) within the 50-byte item
        vals = struct.unpack_from("<5B", buf, off + 30)
    except struct.error:
        return None
    return vals


def status_state(buf: bytes) -> tuple | None:
    """Player tyre compound/age, so a stint boundary is never lost."""
    hdr = decode_header(buf)
    off = HEADER_SIZE + hdr.player_car_index * 55
    try:
        return struct.unpack_from("<3B", buf, off + 25)
    except struct.error:
        return None


def find_final_state(source: Path) -> set[int]:
    """Record indices that must survive subsampling whatever else happens.

    The last SessionHistory packet for each car carries that car's COMPLETE lap history --
    including the final lap, whose time only appears once the lap is finished. Periodic
    sampling will usually miss it, leaving the last lap of every session looking
    incomplete. The same applies to the final LapData and CarStatus.
    """
    last_history: dict[int, int] = {}
    last_lap_data = -1
    last_status = -1

    for index, (_ts, payload) in enumerate(read_legacy(source)):
        if len(payload) < HEADER_SIZE:
            continue
        hdr = decode_header(payload)
        if hdr.session_uid == 0:
            continue
        if hdr.packet_id == 11 and len(payload) > HEADER_SIZE:
            last_history[payload[HEADER_SIZE]] = index
        elif hdr.packet_id == 2:
            last_lap_data = index
        elif hdr.packet_id == 7:
            last_status = index

    forced = set(last_history.values())
    forced.update(i for i in (last_lap_data, last_status) if i >= 0)
    return forced


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("dest", type=Path)
    ap.add_argument("--legacy-probe", action="store_true")
    ap.add_argument("--port", type=int, default=20777)
    args = ap.parse_args()

    if not args.legacy_probe:
        raise SystemExit("only --legacy-probe sources are supported today")

    forced = find_final_state(args.source)
    print(f"pass 1: {len(forced)} end-of-session packets pinned")

    last_sample: dict[int, float] = {}
    codec_samples: Counter[int] = Counter()
    prev_lap: tuple | None = None
    prev_status: tuple | None = None

    kept: Counter[int] = Counter()
    seen: Counter[int] = Counter()
    uid_zero_kept = 0
    change_kept = 0

    writer = RawLogWriter(args.dest, args.port)
    writer.open()
    try:
        for index, (ts, payload) in enumerate(read_legacy(args.source)):
            if len(payload) < HEADER_SIZE:
                continue
            hdr = decode_header(payload)
            pid = hdr.packet_id
            seen[pid] += 1

            keep = index in forced

            # Menu-state traffic: keep it all. The ingest must be tested on the fact that
            # sessionUID == 0 exists and must be discarded (FR-007).
            if keep:
                pass
            elif hdr.session_uid == 0:
                keep = True
                uid_zero_kept += 1
            elif pid in KEEP_ALL:
                keep = True
            elif pid == 2 and (state := lap_state(payload)) is not None and state != prev_lap:
                keep = True  # lap number, pit status or validity changed
                change_kept += 1
                prev_lap = state
            elif pid == 7 and (st := status_state(payload)) is not None and st != prev_status:
                keep = True  # tyre compound or age changed -- a stint boundary
                change_kept += 1
                prev_status = st
            elif pid in SAMPLE_INTERVAL:
                if ts - last_sample.get(pid, -1e9) >= SAMPLE_INTERVAL[pid]:
                    keep = True
                    last_sample[pid] = ts
            elif codec_samples[pid] < CODEC_SAMPLE_COUNT:
                keep = True  # just enough bytes for this codec to be exercised
                codec_samples[pid] += 1

            if keep:
                writer.write(payload, ts)
                kept[pid] += 1
    finally:
        writer.close()

    size = args.dest.stat().st_size
    print(f"wrote {args.dest}  ({size / 1e6:.2f} MB, {writer.records_written} records)")
    print(f"  kept because something changed: {change_kept}")
    print(f"  sessionUID == 0 records kept:   {uid_zero_kept}")
    print()
    print(f"  {'id':<4}{'seen':>9}{'kept':>9}")
    for pid in sorted(seen):
        print(f"  {pid:<4}{seen[pid]:>9}{kept.get(pid, 0):>9}")

    missing = set(seen) - set(kept)
    if missing:
        print(f"\n  WARNING: packet ids present in source but absent from fixture: {missing}")
        return 1
    if size > 5 * 1024 * 1024:
        print(f"\n  WARNING: fixture is {size / 1e6:.1f} MB, over the 5 MB budget")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
