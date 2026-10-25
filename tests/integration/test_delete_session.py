"""T018 -- permanent session deletion (feature 003 US7, research R7).

Every test runs on a throwaway copy of the fixture store, never on real data. Deletion is
the one action in the product that destroys what cannot be regenerated, so most of these
tests check that it does NOT happen when it should not.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from f1dc.capture.status import STATE_RECORDING, RecorderStatus, SessionStatus, write_status
from f1dc.config import Paths
from f1dc.ingest.pipeline import EXIT_BUSY, run_ingest
from f1dc.store import catalog, layout
from f1dc.store.delete import DeleteError, delete_session, raw_logs_for
from f1dc.store.lock import write_lock
from tests.conftest import FIXTURE_LOG_NAME, REFERENCE_UID


@pytest.fixture(scope="module")
def base_store(tmp_path_factory, fixture_path: Path) -> Path:
    root = tmp_path_factory.mktemp("delete-base")
    paths = Paths(root)
    paths.ensure()
    shutil.copy(fixture_path, paths.raw_dir / FIXTURE_LOG_NAME)
    run_ingest(paths, compress_logs=False)
    return root


@pytest.fixture
def store(base_store: Path, tmp_path: Path) -> Paths:
    """A fresh copy per test, raw log included, so resurrection can be tested."""
    shutil.copytree(base_store, tmp_path / "data")
    return Paths(tmp_path / "data")


def everything_still_there(paths: Paths) -> bool:
    return (
        catalog.get_session(paths, REFERENCE_UID) is not None
        and layout.session_dir(paths, REFERENCE_UID).is_dir()
        and len(raw_logs_for(paths, REFERENCE_UID)) == 1
    )


# ---------------------------------------------------------------- it works


def test_a_confirmed_delete_removes_session_and_recording(store: Paths) -> None:
    report = delete_session(store, REFERENCE_UID, "Interlagos")

    assert catalog.get_session(store, REFERENCE_UID) is None
    assert not layout.session_dir(store, REFERENCE_UID).exists()
    assert raw_logs_for(store, REFERENCE_UID) == []
    assert report.left_behind == []
    assert len(report.removed) == 2  # the raw log and the session directory


def test_the_confirmation_ignores_case_and_surrounding_spaces(store: Paths) -> None:
    delete_session(store, REFERENCE_UID, "  interLAGOS ")
    assert catalog.get_session(store, REFERENCE_UID) is None


def test_a_deleted_session_does_not_come_back_on_reingest(store: Paths) -> None:
    """SC-008. The reason the raw log must go too."""
    delete_session(store, REFERENCE_UID, "Interlagos")
    run_ingest(store, force=True, compress_logs=False)
    assert catalog.get_session(store, REFERENCE_UID) is None
    assert catalog.session_count(store) == 0


def test_starred_status_is_cleared(store: Paths) -> None:
    catalog.set_starred(store, REFERENCE_UID, True)
    delete_session(store, REFERENCE_UID, "Interlagos")
    assert REFERENCE_UID not in catalog.get_starred(store)


def test_nothing_is_left_hidden_after_a_clean_delete(store: Paths) -> None:
    delete_session(store, REFERENCE_UID, "Interlagos")
    leftovers = [p.name for p in [*store.raw_dir.iterdir(), *store.sessions_dir.iterdir()]
                 if "deleted" in p.name or "deleting" in p.name]
    assert leftovers == []


# ---------------------------------------------------------------- it refuses


@pytest.mark.parametrize("confirm", [None, "", "   "])
def test_no_confirmation_deletes_nothing(store: Paths, confirm) -> None:
    with pytest.raises(DeleteError) as exc:
        delete_session(store, REFERENCE_UID, confirm)
    assert exc.value.code == "confirmation_required"
    assert everything_still_there(store)


@pytest.mark.parametrize("confirm", ["Monza", "Interlago", "Interlagos Race", REFERENCE_UID])
def test_a_wrong_name_deletes_nothing(store: Paths, confirm: str) -> None:
    """SC-007: only the circuit name itself confirms."""
    with pytest.raises(DeleteError) as exc:
        delete_session(store, REFERENCE_UID, confirm)
    assert exc.value.code == "confirmation_mismatch"
    assert exc.value.status == 400
    assert everything_still_there(store)


def test_an_unknown_session_is_a_404(store: Paths) -> None:
    with pytest.raises(DeleteError) as exc:
        delete_session(store, "123", "Interlagos")
    assert exc.value.status == 404


def test_the_session_being_recorded_is_refused(store: Paths) -> None:
    write_status(store.status_path, RecorderStatus(
        state=STATE_RECORDING,
        session=SessionStatus(REFERENCE_UID, track_id=16, session_type=10, current_lap=3,
                              started_late=False),
    ))
    with pytest.raises(DeleteError) as exc:
        delete_session(store, REFERENCE_UID, "Interlagos")
    assert exc.value.code == "session_recording"
    assert everything_still_there(store)


def test_a_shared_recording_is_refused(store: Paths) -> None:
    """Deleting one session must never silently destroy another from the same file."""
    other = "22222222222222222222"
    dst = layout.session_dir(store, other)
    shutil.copytree(layout.session_dir(store, REFERENCE_UID), dst)
    table = pq.read_table(dst / layout.SESSION_FILE)
    table = table.set_column(table.schema.get_field_index("session_uid"), "session_uid",
                             pa.array([other]))
    pq.write_table(table, dst / layout.SESSION_FILE)  # same recording_id, different session

    with pytest.raises(DeleteError) as exc:
        delete_session(store, REFERENCE_UID, "Interlagos")
    assert exc.value.code == "shared_recording"
    assert everything_still_there(store)


def test_deletion_during_ingest_is_refused(store: Paths) -> None:
    """FR-031: they share a lock and never interleave."""
    with write_lock(store, "ingest"):
        with pytest.raises(DeleteError) as exc:
            delete_session(store, REFERENCE_UID, "Interlagos")
    assert exc.value.code == "busy"
    assert everything_still_there(store)


def test_ingest_during_deletion_waits_its_turn(store: Paths) -> None:
    with write_lock(store, "delete"):
        assert run_ingest(store, force=True, compress_logs=False) == EXIT_BUSY


def test_a_failed_tombstone_is_rolled_back(store: Paths, monkeypatch) -> None:
    """If any rename fails, nothing is deleted -- not half of it."""
    real_rename = Path.rename

    def fail_on_directory(self, target):
        if self.is_dir():
            raise PermissionError("in use")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_on_directory)
    with pytest.raises(DeleteError) as exc:
        delete_session(store, REFERENCE_UID, "Interlagos")
    monkeypatch.undo()

    assert exc.value.code == "delete_failed"
    assert "nothing was deleted" in exc.value.message
    assert everything_still_there(store)


def test_a_partial_removal_is_reported_not_hidden(store: Paths, monkeypatch) -> None:
    """FR-032: never report success that was not achieved."""
    monkeypatch.setattr(shutil, "rmtree", lambda *_a, **_k: (_ for _ in ()).throw(OSError("busy")))
    with pytest.raises(DeleteError) as exc:
        delete_session(store, REFERENCE_UID, "Interlagos")

    assert exc.value.code == "partial_delete"
    assert exc.value.report is not None and exc.value.report.left_behind
    # ...and what was left is hidden and cannot be resurrected
    assert catalog.get_session(store, REFERENCE_UID) is None
    monkeypatch.undo()
    run_ingest(store, force=True, compress_logs=False)
    assert catalog.get_session(store, REFERENCE_UID) is None


def test_a_stale_lock_does_not_block_forever(store: Paths) -> None:
    import os
    import time

    lock = store.derived_dir / ".write.lock"
    lock.write_text("{}", encoding="utf-8")
    old = time.time() - 7200
    os.utime(lock, (old, old))
    delete_session(store, REFERENCE_UID, "Interlagos")
    assert catalog.get_session(store, REFERENCE_UID) is None


# ---------------------------------------------------------------- the CLI


def test_cli_refuses_a_wrong_name(store: Paths) -> None:
    from f1dc.cli.main import main

    code = main(["delete", REFERENCE_UID, "--confirm", "Monza", "--data-dir", str(store.data_dir)])
    assert code == 2
    assert everything_still_there(store)


def test_cli_deletes_with_the_circuit_name(store: Paths) -> None:
    from f1dc.cli.main import main

    code = main(["delete", REFERENCE_UID, "--confirm", "Interlagos", "--data-dir", str(store.data_dir)])
    assert code == 0
    assert catalog.get_session(store, REFERENCE_UID) is None
