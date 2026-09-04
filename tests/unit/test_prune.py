"""T082 -- retention behaviour.

The safety properties matter more than the deletion itself: pruning must never remove a
starred recording, never remove one that was never interpreted, and never touch derived
data. And it is never triggered automatically -- per-frame channels are not stored yet, so
a raw log pruned today could never gain them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from f1dc.capture.rawlog import RawLogWriter
from f1dc.cli.prune import InvalidDuration, parse_duration, run_prune, session_uid_from
from f1dc.config import Paths
from f1dc.store import catalog, layout


def make_log(paths: Paths, uid: str, age_days: int) -> Path:
    stamp = (datetime.now(UTC) - timedelta(days=age_days)).strftime("%Y-%m-%dT%H-%M-%S")
    path = paths.raw_dir / f"{stamp}_{uid}.f1raw"
    with RawLogWriter(path, 20777) as writer:
        writer.write(b"x" * 64, 0.0)
    return path


def mark_ingested(paths: Paths, uid: str) -> None:
    directory = layout.session_dir(paths, uid)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / layout.SESSION_FILE).write_bytes(b"parquet-stand-in")


@pytest.fixture
def store(tmp_path: Path) -> Paths:
    paths = Paths(tmp_path)
    paths.ensure()
    return paths


# ---------------------------------------------------------------- duration parsing


@pytest.mark.parametrize(
    ("text", "days"),
    [("90d", 90), ("12w", 84), ("6m", 180), ("1y", 365), ("30D", 30)],
)
def test_duration_forms(text: str, days: int) -> None:
    assert parse_duration(text) == timedelta(days=days)


@pytest.mark.parametrize("text", ["", "90", "abc", "-1d", "90 days"])
def test_invalid_durations_are_rejected(text: str) -> None:
    with pytest.raises(InvalidDuration):
        parse_duration(text)


def test_session_uid_is_recovered_from_the_filename() -> None:
    assert session_uid_from(Path("2026-09-04T11-04-12_15975277775803518192.f1raw")) == (
        "15975277775803518192"
    )
    assert session_uid_from(Path("2026-09-04T11-04-12_123.f1raw.zst")) == "123"


# ---------------------------------------------------------------- what gets deleted


def test_an_old_ingested_log_is_deleted(store: Paths) -> None:
    log = make_log(store, "111", age_days=200)
    mark_ingested(store, "111")
    assert run_prune(store, "90d", assume_yes=True) == 0
    assert not log.exists()


def test_a_recent_log_is_kept(store: Paths) -> None:
    log = make_log(store, "222", age_days=10)
    mark_ingested(store, "222")
    run_prune(store, "90d", assume_yes=True)
    assert log.exists()


def test_a_starred_log_is_never_deleted(store: Paths) -> None:
    log = make_log(store, "333", age_days=999)
    mark_ingested(store, "333")
    catalog.set_starred(store, "333", True)
    run_prune(store, "1d", assume_yes=True)
    assert log.exists(), "starred recordings must survive any retention window"


def test_a_never_ingested_log_is_kept(store: Paths) -> None:
    """Deleting it would destroy the only copy of something nothing else represents."""
    log = make_log(store, "444", age_days=999)
    run_prune(store, "1d", assume_yes=True)
    assert log.exists()


def test_dry_run_deletes_nothing(store: Paths) -> None:
    log = make_log(store, "555", age_days=999)
    mark_ingested(store, "555")
    assert run_prune(store, "1d", dry_run=True, assume_yes=True) == 0
    assert log.exists()


def test_derived_data_is_never_touched(store: Paths) -> None:
    make_log(store, "666", age_days=999)
    mark_ingested(store, "666")
    derived = layout.session_dir(store, "666") / layout.SESSION_FILE
    run_prune(store, "1d", assume_yes=True)
    assert derived.exists(), "pruning must only remove raw logs"


def test_an_invalid_window_is_an_error_not_a_deletion(store: Paths) -> None:
    log = make_log(store, "777", age_days=999)
    mark_ingested(store, "777")
    assert run_prune(store, "forever", assume_yes=True) == 2
    assert log.exists()


def test_nothing_to_prune_is_not_an_error(store: Paths) -> None:
    assert run_prune(store, "90d", assume_yes=True) == 0


def test_pruning_is_not_wired_to_any_automatic_trigger() -> None:
    """Per plan.md: automatic pruning ships disabled until features 002 and 003 land.

    If channel extraction arrived after a raw log had been pruned, that session could
    never gain channels -- so nothing may call run_prune except the explicit command.
    """
    import subprocess
    import sys

    source_root = Path(__file__).resolve().parents[2] / "src"
    result = subprocess.run(
        [sys.executable, "-c", "pass"], capture_output=True, check=False
    )
    assert result.returncode == 0  # sanity

    callers = [
        path
        for path in source_root.rglob("*.py")
        if "run_prune" in path.read_text(encoding="utf-8")
        and path.name not in ("prune.py", "main.py")
    ]
    assert callers == [], f"run_prune is reachable from {[p.name for p in callers]}"
