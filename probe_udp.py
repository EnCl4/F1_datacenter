#!/usr/bin/env python3
"""
F1 23 UDP telemetry probe.

Pre-spec diagnostic. Three jobs:
  1. Confirm the game is actually sending anything at all.
  2. Validate the 29-byte packet header and report which packet types arrive,
     at what rate, and at what size (sizes are how we sanity-check struct
     definitions against the official spec).
  3. Write the raw wire stream to disk so a real capture can be replayed
     against the parser later. This file is the calibration fixture.

Stdlib only. Ctrl+C to stop.

Usage:
    python probe_udp.py
    python probe_udp.py --port 20777 --out calibration.bin
"""

import argparse
import collections
import socket
import struct
import sys
import time

# F1 23 (packet format 2023) packet header, little-endian, packed. 29 bytes.
#   uint16 packetFormat        uint8  gameYear
#   uint8  gameMajorVersion    uint8  gameMinorVersion
#   uint8  packetVersion       uint8  packetId
#   uint64 sessionUID          float  sessionTime
#   uint32 frameIdentifier     uint32 overallFrameIdentifier
#   uint8  playerCarIndex      uint8  secondaryPlayerCarIndex
HEADER = struct.Struct("<HBBBBBQfIIBB")
assert HEADER.size == 29

PACKET_NAMES = {
    0: "Motion",
    1: "Session",
    2: "LapData",
    3: "Event",
    4: "Participants",
    5: "CarSetups",
    6: "CarTelemetry",
    7: "CarStatus",
    8: "FinalClassification",
    9: "LobbyInfo",
    10: "CarDamage",
    11: "SessionHistory",
    12: "TyreSets",
    13: "MotionEx",
}

# Raw log record framing: uint32 payload length + double receive timestamp.
RECORD = struct.Struct("<Id")


class Stats:
    def __init__(self):
        self.count = 0
        self.sizes = set()
        self.last_frame = None
        self.backwards = 0  # frameIdentifier going backwards == flashback


def main():
    ap = argparse.ArgumentParser(description="F1 23 UDP telemetry probe")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=20777)
    ap.add_argument("--out", default="calibration.bin",
                    help="raw wire stream output (default: calibration.bin)")
    ap.add_argument("--interval", type=float, default=2.0,
                    help="seconds between status reports")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    except OSError:
        pass
    sock.bind((args.host, args.port))
    sock.settimeout(0.5)

    stats = collections.defaultdict(Stats)
    events = []
    sessions = set()
    total_bytes = 0
    started = None
    window_start = time.monotonic()
    window_counts = collections.Counter()
    first_report_done = False

    print("listening on %s:%d -> %s" % (args.host, args.port, args.out))
    print("start the game and enter a session. Ctrl+C to stop.\n")

    out = open(args.out, "wb")
    try:
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                data = None

            now = time.monotonic()

            if data:
                out.write(RECORD.pack(len(data), now))
                out.write(data)
                total_bytes += len(data)

                if len(data) >= HEADER.size:
                    (fmt, year, major, minor, pver, pid, suid,
                     stime, frame, oframe, pcar, scar) = HEADER.unpack_from(data)

                    if started is None:
                        started = now
                        print("first packet: format=%d gameYear=%d v%d.%d "
                              "playerCarIndex=%d" % (fmt, year, major, minor, pcar))
                        if fmt != 2023:
                            print("  !! packet format is %d, expected 2023 -- "
                                  "check UDP Format in the game settings" % fmt)
                        print()

                    sessions.add(suid)
                    s = stats[pid]
                    s.count += 1
                    s.sizes.add(len(data))
                    if s.last_frame is not None and frame < s.last_frame:
                        s.backwards += 1
                    s.last_frame = frame
                    window_counts[pid] += 1

                    if pid == 3 and len(data) >= HEADER.size + 4:
                        code = data[HEADER.size:HEADER.size + 4].decode(
                            "ascii", "replace")
                        if not events or events[-1][0] != code:
                            events.append((code, stime))
                            print("  event %s @ t=%.1fs" % (code, stime))

            elapsed = now - window_start
            if elapsed >= args.interval and started is not None:
                report(stats, window_counts, elapsed, total_bytes,
                       now - started, sessions, first_report_done)
                first_report_done = True
                window_counts.clear()
                window_start = now

    except KeyboardInterrupt:
        print("\n\nstopped.")
    finally:
        out.close()
        sock.close()
        summary(stats, events, sessions, total_bytes, args.out)


def report(stats, window, elapsed, total_bytes, uptime, sessions, seen_before):
    if seen_before:
        # redraw in place-ish: just separate blocks
        print()
    print("--- %5.1fs  %6.2f MB  %d session(s) ---" % (
        uptime, total_bytes / 1e6, len(sessions)))
    print("  %-3s %-21s %8s %8s  %s" % ("id", "name", "total", "Hz", "sizes"))
    for pid in sorted(stats):
        s = stats[pid]
        hz = window.get(pid, 0) / elapsed if elapsed > 0 else 0.0
        print("  %-3d %-21s %8d %8.1f  %s" % (
            pid, PACKET_NAMES.get(pid, "UNKNOWN"), s.count, hz,
            ",".join(str(x) for x in sorted(s.sizes))))


def summary(stats, events, sessions, total_bytes, path):
    print("\n===== capture summary =====")
    if not stats:
        print("NO PACKETS RECEIVED.")
        print("  - is UDP Telemetry set to On?")
        print("  - is the IP 127.0.0.1 and the port 20777?")
        print("  - are you actually in a session (not the main menu)?")
        print("  - is another app already bound to the port?")
        return

    print("raw log:   %s (%.1f MB)" % (path, total_bytes / 1e6))
    print("sessions:  %d unique sessionUID" % len(sessions))
    print("\npacket types seen:")
    print("  %-3s %-21s %8s  %s" % ("id", "name", "count", "observed sizes"))
    for pid in sorted(stats):
        s = stats[pid]
        print("  %-3d %-21s %8d  %s" % (
            pid, PACKET_NAMES.get(pid, "UNKNOWN"), s.count,
            ",".join(str(x) for x in sorted(s.sizes))))

    missing = [PACKET_NAMES[p] for p in sorted(PACKET_NAMES) if p not in stats]
    if missing:
        print("\nnot seen: %s" % ", ".join(missing))

    flash = [(p, s.backwards) for p, s in sorted(stats.items()) if s.backwards]
    if flash:
        print("\nframeIdentifier went backwards (flashback / restart):")
        for pid, n in flash:
            print("  %-21s %d time(s)" % (PACKET_NAMES.get(pid, pid), n))
    else:
        print("\nno flashback detected -- if you meant to trigger one, "
              "it did not land in this capture.")

    if events:
        print("\nevents: %s" % " ".join(c for c, _ in events))


if __name__ == "__main__":
    sys.exit(main())
