"""T047 -- ingest is idempotent and re-runnable.

FR-015, SC-005 and constitution principle VII. This is what makes reprocessing history
routine rather than risky: a parser improvement can be rolled across every session ever
recorded, repeatedly, without duplicating anything or producing different answers.

Idempotence here is structural, not careful: each session is written to a temporary
directory and renamed into place.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from f1dc.config import Paths
from f1dc.ingest.compress import compress_log, is_compressed, open_raw
from f1dc.ingest.pipeline import EXIT_NO_LOGS, run_ingest
from f1dc.store import catalog, layout
from tests.conftest import FIXTURE_LOG_NAME, REFERENCE_LAPS, REFERENCE_UID


#: The files idempotence is defined over: the interpreted result.
#:
#: recordings.parquet is deliberately excluded. It carries provenance -- including
#: `ingested_at`, the wall-clock time the run happened -- which is by definition
#: different on a second run. That is not "the result" under FR-015; the session, its
#: laps and its stints are. `test_provenance_is_the_only_thing_that_changes` pins that
#: distinction so the exclusion cannot quietly widen.
RESULT_FILES = (layout.SESSION_FILE, layout.LAPS_FILE, layout.STINTS_FILE)


def digest(paths: Paths) -> dict[str, str]:
    """Content hash of the interpreted result for every session in the store."""
    out: dict[str, str] = {}
    for directory in layout.iter_session_dirs(paths):
        for name in RESULT_FILES:
            file = directory / name
            if file.exists():
                out[f"{directory.name}/{name}"] = hashlib.sha256(file.read_bytes()).hexdigest()
    return out


@pytest.fixture
def store(tmp_path: Path, fixture_path: Path) -> Paths:
    paths = Paths(tmp_path)
    paths.ensure()
    shutil.copy(fixture_path, paths.raw_dir / FIXTURE_LOG_NAME)
    return paths


def test_re_ingesting_produces_identical_bytes(store: Paths) -> None:
    run_ingest(store, compress_logs=False)
    before = digest(store)

    run_ingest(store, force=True, compress_logs=False)
    after = digest(store)

    assert before == after, "re-ingest changed the derived store"
    assert before, "nothing was written at all"


def test_provenance_is_the_only_thing_that_changes(store: Paths) -> None:
    """Re-running changes when it was ingested and nothing else.

    This is the counterpart to the exclusion above: if any interpreted field started
    drifting between runs, it would show up here rather than being hidden by it.
    """
    import duckdb

    def recording_row() -> dict:
        parquet = (layout.session_dir(store, REFERENCE_UID) / layout.RECORDINGS_FILE).as_posix()
        with duckdb.connect(":memory:") as con:
            cursor = con.execute(f"SELECT * FROM read_parquet('{parquet}')")
            columns = [d[0] for d in cursor.description]
            return dict(zip(columns, cursor.fetchone(), strict=True))

    run_ingest(store, compress_logs=False)
    before = recording_row()
    run_ingest(store, force=True, compress_logs=False)
    after = recording_row()

    differing = {k for k in before if before[k] != after[k]}
    assert differing <= {"ingested_at"}, f"unexpected drift in {differing - {'ingested_at'}}"


def test_re_ingesting_creates_no_duplicate_sessions(store: Paths) -> None:
    run_ingest(store, compress_logs=False)
    assert catalog.session_count(store) == 1

    for _ in range(3):
        run_ingest(store, force=True, compress_logs=False)
    assert catalog.session_count(store) == 1

    total, items = catalog.list_sessions(store)
    assert total == 1
    assert len({item["session_uid"] for item in items}) == 1


def test_lap_content_is_stable_across_runs(store: Paths) -> None:
    run_ingest(store, compress_logs=False)
    first = catalog.get_laps(store, REFERENCE_UID)
    run_ingest(store, force=True, compress_logs=False)
    second = catalog.get_laps(store, REFERENCE_UID)
    assert first == second
    assert {lap["lap_number"]: lap["lap_time_ms"] for lap in first} == REFERENCE_LAPS


def test_a_second_run_without_force_skips_already_current_sessions(store: Paths) -> None:
    run_ingest(store, compress_logs=False)
    before = digest(store)
    assert run_ingest(store, compress_logs=False) == 0
    assert digest(store) == before


def test_no_temporary_directories_are_left_behind(store: Paths) -> None:
    run_ingest(store, compress_logs=False)
    leftovers = [p.name for p in store.sessions_dir.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_ingesting_with_no_logs_reports_it(tmp_path: Path) -> None:
    paths = Paths(tmp_path)
    paths.ensure()
    assert run_ingest(paths) == EXIT_NO_LOGS


def test_starring_a_session_does_not_disturb_idempotence(store: Paths) -> None:
    """Starred state is user data, deliberately outside the ingest output."""
    run_ingest(store, compress_logs=False)
    before = digest(store)

    catalog.set_starred(store, REFERENCE_UID, True)
    assert catalog.get_session(store, REFERENCE_UID)["starred"] is True

    run_ingest(store, force=True, compress_logs=False)
    assert digest(store) == before
    assert catalog.get_session(store, REFERENCE_UID)["starred"] is True


# ---------------------------------------------------------------- compression


def test_compression_round_trips_the_raw_log(store: Paths) -> None:
    log = store.raw_dir / FIXTURE_LOG_NAME
    original = log.read_bytes()

    compressed = compress_log(log)
    assert is_compressed(compressed)
    assert not log.exists(), "the original should be removed once verified"

    with open_raw(compressed) as handle:
        assert handle.read() == original


def test_a_compressed_log_ingests_identically(store: Paths) -> None:
    run_ingest(store, compress_logs=False)
    uncompressed = digest(store)

    shutil.rmtree(store.sessions_dir)
    store.sessions_dir.mkdir(parents=True)
    compress_log(store.raw_dir / FIXTURE_LOG_NAME)
    run_ingest(store, compress_logs=False)

    assert digest(store) == uncompressed, "compression changed the interpreted result"


def test_compression_actually_saves_space(store: Paths) -> None:
    log = store.raw_dir / FIXTURE_LOG_NAME
    before = log.stat().st_size
    after = compress_log(log).stat().st_size
    assert after < before
