"""T016 -- permanently deleting a session (feature 003 User Story 7, research R7).

The only write the web app may perform (constitution 1.1.0). It destroys the one artifact
the system cannot regenerate, so it is built to fail safe:

1. **Every check before anything moves.** The typed confirmation must equal the circuit
   name -- checked HERE, never trusted from a page (FR-028). The session being recorded
   cannot be deleted, and nor can a recording that also holds another session (FR-030).
2. **The write lock**, shared with ingest, so the two never interleave (FR-031).
3. **Tombstone first, with rollback.** The raw log is renamed to ``*.deleted`` (ingest
   ignores it) and the session directory to ``.deleting-<uid>`` (the library ignores it).
   If any rename fails, every rename is undone and NOTHING is deleted. Order matters:
   had the derived data been removed first and the raw log then failed to delete, the next
   ingest would silently resurrect the session (SC-008).
4. **Then remove**, and report exactly what went and what did not (FR-032). Anything left
   behind is already tombstoned: invisible, and unable to come back.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from f1dc.capture.status import read_status
from f1dc.config import Paths
from f1dc.store import catalog, layout
from f1dc.store.lock import WriteLockBusy, write_lock

TOMBSTONE_SUFFIX = ".deleted"
DELETING_PREFIX = ".deleting-"


@dataclass
class DeleteReport:
    session_uid: str
    removed: list[str] = field(default_factory=list)
    left_behind: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "deleted": not self.left_behind,
            "session_uid": self.session_uid,
            "removed": self.removed,
            "left_behind": self.left_behind,
        }


class DeleteError(Exception):
    def __init__(
        self, code: str, message: str, status: int, report: DeleteReport | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.report = report


def raw_logs_for(paths: Paths, session_uid: str) -> list[Path]:
    return [
        p for p in layout.raw_logs(paths)
        if p.name.split(".f1raw")[0].endswith(f"_{session_uid}")
    ]


def _other_sessions_sharing(paths: Paths, session: dict) -> list[str]:
    """Sessions interpreted from the same recording as this one."""
    with catalog.connect(paths) as con:
        rows = con.execute(
            f"SELECT session_uid FROM {catalog.SESSION_VIEW} "
            f"WHERE recording_id = ? AND session_uid <> ?",
            [session["recording_id"], session["session_uid"]],
        ).fetchall()
    return [r[0] for r in rows]


def check(paths: Paths, session_uid: str, confirm: str | None) -> dict:
    """Every refusal, before anything is touched. Returns the session."""
    session = catalog.get_session(paths, session_uid)
    if session is None:
        raise DeleteError("session_not_found", f"No session with uid {session_uid}", 404)

    if confirm is None or not confirm.strip():
        raise DeleteError(
            "confirmation_required",
            f"Type the circuit name ({session['track_name']}) to confirm the deletion",
            400,
        )
    if confirm.strip().casefold() != session["track_name"].strip().casefold():
        raise DeleteError(
            "confirmation_mismatch",
            f"The name typed does not match {session['track_name']}; nothing was deleted",
            400,
        )

    status = read_status(paths.status_path)
    live = status.get("session") or {}
    if status.get("recording") and str(live.get("uid")) == session_uid:
        raise DeleteError(
            "session_recording",
            "This session is being recorded right now; stop the recorder before deleting it",
            409,
        )

    others = _other_sessions_sharing(paths, session)
    if others:
        raise DeleteError(
            "shared_recording",
            f"Its recording also holds {len(others)} other session(s) "
            f"({', '.join(others)}); deleting it would destroy them too, so nothing was deleted",
            409,
        )
    return session


def delete_session(paths: Paths, session_uid: str, confirm: str | None) -> DeleteReport:
    check(paths, session_uid, confirm)
    report = DeleteReport(session_uid)

    try:
        with write_lock(paths, f"delete {session_uid}"):
            moved: list[tuple[Path, Path]] = []
            targets = [(raw, raw.with_name(raw.name + TOMBSTONE_SUFFIX))
                       for raw in raw_logs_for(paths, session_uid)]
            directory = layout.session_dir(paths, session_uid)
            if directory.exists():
                targets.append((directory, paths.sessions_dir / f"{DELETING_PREFIX}{session_uid}"))

            # 3. Tombstone everything, or nothing.
            try:
                for source, tombstone in targets:
                    source.rename(tombstone)
                    moved.append((source, tombstone))
            except OSError as exc:
                for source, tombstone in reversed(moved):
                    try:
                        tombstone.rename(source)
                    except OSError:
                        pass
                raise DeleteError(
                    "delete_failed",
                    f"Could not delete {source.name} ({exc}); nothing was deleted",
                    500,
                ) from exc

            # 4. Remove. Failures here leave invisible, non-resurrectable tombstones.
            for source, tombstone in moved:
                try:
                    if tombstone.is_dir():
                        shutil.rmtree(tombstone)
                    else:
                        tombstone.unlink()
                    report.removed.append(str(source))
                except OSError:
                    report.left_behind.append(str(tombstone))

            catalog.set_starred(paths, session_uid, False)
    except WriteLockBusy as exc:
        raise DeleteError(
            "busy",
            f"Recordings are being processed by {exc.holder}; try again when it finishes",
            409,
        ) from exc

    if report.left_behind:
        raise DeleteError(
            "partial_delete",
            "The session was removed from the library, but some files could not be "
            "deleted. They are hidden and cannot come back; they can be removed by hand.",
            500,
            report,
        )
    return report
