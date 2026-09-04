"""T081 -- `f1dc doctor`, the command that answers "why isn't it recording?".

Checks run in the order things actually fail, and each one says what to do rather than
just what is wrong. If the game is running it also listens briefly and compares observed
packet sizes against the expected 2023 wire sizes -- the check that catches a game patch
changing the format before it silently corrupts a season of data.
"""

from __future__ import annotations

import shutil
import socket
import time
from collections import Counter
from pathlib import Path

from f1dc.config import ConfigError, detect_sync_root, load_paths
from f1dc.wire.f1_2023 import OBSERVED_WIRE_SIZES, UNDECODED_PACKET_IDS
from f1dc.wire.f1_2023.enums import session_type_name, track_name
from f1dc.wire.header import HEADER_SIZE, decode_header

OK = "  [ok]  "
WARN = "  [warn]"
FAIL = "  [FAIL]"

MIN_FREE_BYTES = 5 * 1024**3
BYTES_PER_HOUR = 1.3e9


def run_doctor(
    data_dir: Path | str | None,
    *,
    port: int = 20777,
    listen_seconds: float = 10.0,
    allow_sync_root: bool = False,
) -> int:
    problems = 0

    print("F1 Data Center -- diagnostics\n")

    # 1. Data directory ------------------------------------------------------------
    print("data directory")
    try:
        paths = load_paths(data_dir, allow_sync_root=allow_sync_root)
    except ConfigError as exc:
        print(f"{FAIL} {exc}")
        return 1

    print(f"{OK} {paths.data_dir}")
    if offender := detect_sync_root(paths.data_dir):
        print(f"{WARN} inside a cloud-sync folder ({offender}) -- this will cost you data")
        problems += 1

    try:
        probe = paths.raw_dir / ".doctor-probe"
        probe.write_bytes(b"")
        probe.unlink()
        print(f"{OK} writable")
    except OSError as exc:
        print(f"{FAIL} not writable: {exc}")
        return 1

    # 2. Disk space -----------------------------------------------------------------
    free = shutil.disk_usage(paths.raw_dir).free
    hours = free / BYTES_PER_HOUR
    print("\ndisk space")
    if free < MIN_FREE_BYTES:
        print(f"{FAIL} {free / 1024**3:.1f} GB free -- recording needs at least 5 GB")
        problems += 1
    else:
        print(f"{OK} {free / 1024**3:.1f} GB free (about {hours:.0f} hours of capture)")

    # 3. The port -------------------------------------------------------------------
    print(f"\nUDP port {port}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", port))
        print(f"{OK} available")
    except OSError:
        sock.close()
        print(f"{FAIL} already in use -- another app is receiving telemetry")
        print("         close it, or enable UDP Broadcast Mode in the game")
        return 1

    # 4. Live traffic ---------------------------------------------------------------
    print(f"\nlistening for {listen_seconds:.0f}s (start a session in the game now)")
    sizes: dict[int, Counter] = {}
    counts: Counter = Counter()
    session_info: tuple[int, int] | None = None
    formats: set[int] = set()

    sock.settimeout(0.5)
    deadline = time.monotonic() + listen_seconds
    try:
        while time.monotonic() < deadline:
            try:
                data = sock.recv(4096)
            except TimeoutError:
                continue
            if len(data) < HEADER_SIZE:
                continue
            header = decode_header(data)
            formats.add(header.packet_format)
            counts[header.packet_id] += 1
            sizes.setdefault(header.packet_id, Counter())[len(data)] += 1
            if header.packet_id == 1 and len(data) >= HEADER_SIZE + 8:
                session_info = (
                    int.from_bytes(data[HEADER_SIZE + 7 : HEADER_SIZE + 8], "little", signed=True),
                    data[HEADER_SIZE + 6],
                )
    finally:
        sock.close()

    if not counts:
        print(f"{FAIL} no telemetry received")
        print("         - is UDP Telemetry set to On in the game?")
        print("         - is the IP 127.0.0.1 and the port 20777?")
        print("         - are you in a session, rather than the menus?")
        return 1

    total = sum(counts.values())
    rate = total / listen_seconds
    print(f"{OK} {total} packets ({rate:.0f}/s across all types)")

    if session_info:
        track, session_type = session_info
        print(f"{OK} {track_name(track)} -- {session_type_name(session_type)}")

    # 5. Wire format ----------------------------------------------------------------
    print("\nwire format")
    if formats != {2023}:
        print(f"{FAIL} packet format {sorted(formats)}; this build understands 2023")
        print("         set UDP Format to 2023, or this build needs updating")
        problems += 1
    else:
        print(f"{OK} 2023")

    mismatches = []
    for packet_id, observed in sorted(sizes.items()):
        expected = OBSERVED_WIRE_SIZES.get(packet_id)
        got = sorted(observed)
        if expected is None:
            mismatches.append(f"unexpected packet id {packet_id} ({got})")
        elif got != [expected]:
            mismatches.append(f"id {packet_id}: got {got}, expected {expected}")

    if mismatches:
        print(f"{FAIL} packet sizes do not match the 2023 specification:")
        for line in mismatches:
            print(f"         {line}")
        print("         the game may have been patched; do not trust interpreted data")
        problems += 1
    else:
        print(f"{OK} all {len(sizes)} packet types match their expected sizes")

    decoded = [p for p in sizes if p not in UNDECODED_PACKET_IDS]
    print(f"{OK} {len(decoded)} type(s) decoded, "
          f"{len(sizes) - len(decoded)} preserved but not yet interpreted")

    print("\n" + ("all good" if problems == 0 else f"{problems} problem(s) found"))
    return 0 if problems == 0 else 1
