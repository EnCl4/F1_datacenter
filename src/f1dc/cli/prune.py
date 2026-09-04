"""T082 -- `f1dc prune`, retention for raw logs.

**Never wired to an automatic trigger**, and that is deliberate. Per-frame telemetry
channels are not persisted yet; feature 002 will add them by re-ingesting the raw logs
you already have. A raw log pruned before then could never gain them, so automatic
deletion stays off until that work has landed.

Derived data is never deleted here -- only the raw logs, and never a starred one.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from f1dc.config import Paths
from f1dc.store import catalog, layout

DURATION = re.compile(r"^(\d+)([dwmy])$")
UNITS = {"d": 1, "w": 7, "m": 30, "y": 365}


class InvalidDuration(ValueError):
    pass


def parse_duration(text: str) -> timedelta:
    match = DURATION.match(text.strip().lower())
    if not match:
        raise InvalidDuration(f"cannot read '{text}'; use forms like 90d, 12w, 6m, 1y")
    amount, unit = match.groups()
    return timedelta(days=int(amount) * UNITS[unit])


def session_uid_from(path: Path) -> str:
    return path.name.split(".f1raw")[0].split("_")[-1]


def captured_at_from(path: Path) -> datetime:
    stem = path.name.split(".f1raw")[0].split("_")[0]
    try:
        return datetime.strptime(stem, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def run_prune(
    paths: Paths,
    older_than: str = "90d",
    *,
    dry_run: bool = False,
    assume_yes: bool = False,
) -> int:
    try:
        window = parse_duration(older_than)
    except InvalidDuration as exc:
        print(f"error: {exc}")
        return 2

    cutoff = datetime.now(UTC) - window
    starred = catalog.get_starred(paths)
    ingested = layout.ingested_session_uids(paths)

    doomed: list[tuple[Path, int]] = []
    kept_starred = 0
    kept_uningested = 0

    for log in layout.raw_logs(paths):
        if captured_at_from(log) >= cutoff:
            continue
        uid = session_uid_from(log)
        if uid in starred:
            kept_starred += 1
            continue
        if uid not in ingested:
            # Never delete a raw log whose session was never interpreted -- that would
            # destroy the only copy of something no derived data represents.
            kept_uningested += 1
            continue
        doomed.append((log, log.stat().st_size))

    if not doomed:
        print(f"nothing to prune older than {older_than}")
        if kept_starred:
            print(f"  {kept_starred} starred recording(s) kept regardless of age")
        if kept_uningested:
            print(f"  {kept_uningested} never-ingested recording(s) kept")
        return 0

    total = sum(size for _p, size in doomed)
    print(f"{len(doomed)} raw log(s) older than {older_than}, {total / 1e9:.2f} GB:")
    for log, size in doomed:
        print(f"  {log.name}  ({size / 1e6:.0f} MB)")
    if kept_starred:
        print(f"\n  keeping {kept_starred} starred recording(s)")
    if kept_uningested:
        print(f"  keeping {kept_uningested} never-ingested recording(s)")

    print(
        "\nNote: derived sessions and laps are NOT affected. What is lost is the ability "
        "to re-interpret these sessions under a future parser."
    )

    if dry_run:
        print("\n--dry-run: nothing deleted")
        return 0

    if not assume_yes:
        try:
            answer = input("\ndelete these raw logs? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("cancelled")
            return 0

    freed = 0
    for log, size in doomed:
        try:
            log.unlink()
            freed += size
        except OSError as exc:
            print(f"  could not delete {log.name}: {exc}")

    print(f"\nfreed {freed / 1e9:.2f} GB")
    return 0
