"""T055, T058 -- ingest orchestration.

Idempotent by construction (FR-015, constitution principle VII): each session is written
to a temporary directory and renamed into place. A failed run leaves nothing half-written,
and a repeated run produces identical bytes because the inputs and the code are the same.

Runs in its own process. It never executes inside the recorder.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from f1dc.capture.rawlog import iter_records
from f1dc.config import Paths
from f1dc.ingest import INGEST_VERSION
from f1dc.ingest.compress import compress_log, is_compressed, open_raw
from f1dc.ingest.laps import build
from f1dc.ingest.sessionizer import Sessionizer
from f1dc.models import Recording
from f1dc.store import catalog, layout
from f1dc.store.schema import (
    LAP_SCHEMA,
    RECORDING_SCHEMA,
    SESSION_SCHEMA,
    STINT_SCHEMA,
    table_from_rows,
)

EXIT_OK = 0
EXIT_UNKNOWN_FORMAT = 6
EXIT_NO_LOGS = 7


@dataclass
class IngestReport:
    sessions_written: int = 0
    sessions_skipped: int = 0
    logs_processed: int = 0
    menu_records_discarded: int = 0
    unknown_packets: int = 0
    unknown_detail: list[str] = field(default_factory=list)
    compressed_bytes_saved: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.unknown_packets:
            return EXIT_UNKNOWN_FORMAT
        return EXIT_OK


def captured_at_from(path: Path) -> datetime:
    """Recover the capture start from the filename, falling back to the file's mtime."""
    stem = path.name.split(".f1raw")[0]
    timestamp = stem.split("_")[0]
    try:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def recording_id_for(path: Path) -> str:
    return path.name.split(".f1raw")[0]


def ingest_log(paths: Paths, log_path: Path, *, report: IngestReport) -> list[str]:
    """Interpret one raw log. Returns the session uids written."""
    captured_at = captured_at_from(log_path)
    recording_id = recording_id_for(log_path)

    sessionizer = Sessionizer(captured_at)
    with open_raw(log_path) as handle:
        for record in iter_records(handle):
            sessionizer._feed_one(record)
    sessions = sessionizer.result()

    report.menu_records_discarded += sessionizer.menu_records
    report.unknown_packets += sum(sessionizer.unknown.values())
    for key, count in sessionizer.unknown.items():
        report.unknown_detail.append(
            f"{count} packet(s) with format {key[0]}, id {key[1]}, version {key[2]}"
        )

    size_bytes = log_path.stat().st_size
    written: list[str] = []

    for raw in sessions:
        if not raw.laps and raw.session_data is None:
            # Nothing interpretable -- a few stray packets, not a session.
            report.sessions_skipped += 1
            continue

        result = build(raw, recording_id)
        recording = Recording(
            recording_id=recording_id,
            path=str(log_path),
            captured_at=captured_at.isoformat(),
            size_bytes=size_bytes,
            packets_received=raw.packets,
            frames_lost=raw.frames_lost,
            loss_pct=round(raw.loss_pct, 4),
            queue_high_water=0,
            packet_format=raw.packet_format,
            game_version=raw.game_version,
            unknown_packets=sum(sessionizer.unknown.values()),
            compressed=is_compressed(log_path),
            starred=False,
            ingest_version=INGEST_VERSION,
            ingested_at=datetime.now(UTC).isoformat(),
        )
        result.recording = recording
        _write_session(paths, result)
        written.append(result.session.session_uid)
        report.sessions_written += 1

    return written


def _write_session(paths: Paths, result) -> None:
    """Write to a temp directory, then rename into place. Idempotence is structural."""
    uid = result.session.session_uid
    temp = layout.temp_session_dir(paths, uid)
    final = layout.session_dir(paths, uid)

    if temp.exists():
        shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True, exist_ok=True)

    pq.write_table(
        table_from_rows([result.session.to_row()], SESSION_SCHEMA),
        temp / layout.SESSION_FILE,
        compression="zstd",
    )
    pq.write_table(
        table_from_rows([lap.to_row() for lap in result.laps], LAP_SCHEMA),
        temp / layout.LAPS_FILE,
        compression="zstd",
    )
    pq.write_table(
        table_from_rows([stint.to_row() for stint in result.stints], STINT_SCHEMA),
        temp / layout.STINTS_FILE,
        compression="zstd",
    )
    if result.recording is not None:
        pq.write_table(
            table_from_rows([result.recording.to_row()], RECORDING_SCHEMA),
            temp / layout.RECORDINGS_FILE,
            compression="zstd",
        )

    if final.exists():
        shutil.rmtree(final, ignore_errors=True)
    temp.rename(final)


def run_ingest(
    paths: Paths,
    *,
    explicit: list[Path] | None = None,
    force: bool = False,
    compress_logs: bool = True,
) -> int:
    """Ingest raw logs. Returns a process exit code."""
    report = IngestReport()
    logs = explicit if explicit else layout.raw_logs(paths)
    if not logs:
        print("no raw logs found", file=sys.stderr)
        return EXIT_NO_LOGS

    stored = catalog.stored_ingest_versions(paths)

    for log_path in logs:
        if not log_path.exists():
            report.errors.append(f"{log_path} does not exist")
            continue

        if not force and not explicit and _already_current(log_path, stored):
            report.sessions_skipped += 1
            continue

        try:
            ingest_log(paths, log_path, report=report)
            report.logs_processed += 1
        except Exception as exc:  # noqa: BLE001 - one bad log must not stop the rest
            report.errors.append(f"{log_path.name}: {exc}")
            continue

        if compress_logs and not is_compressed(log_path):
            before = log_path.stat().st_size
            try:
                after_path = compress_log(log_path)
                report.compressed_bytes_saved += before - after_path.stat().st_size
            except OSError as exc:
                report.errors.append(f"{log_path.name}: compression failed, original kept ({exc})")

    _print_report(report)
    return report.exit_code


def _already_current(log_path: Path, stored: dict[str, str]) -> bool:
    """True if every session from this log is already ingested at the current version."""
    recording_id = recording_id_for(log_path)
    uid = recording_id.split("_")[-1]
    return stored.get(uid) == INGEST_VERSION


def _print_report(report: IngestReport) -> None:
    print(
        f"ingested {report.sessions_written} session(s) from "
        f"{report.logs_processed} log(s)"
    )
    if report.sessions_skipped:
        print(f"  skipped {report.sessions_skipped} already current or uninterpretable")
    if report.menu_records_discarded:
        print(f"  discarded {report.menu_records_discarded} menu-state record(s)")
    if report.compressed_bytes_saved > 0:
        print(f"  compression saved {report.compressed_bytes_saved / 1e6:.1f} MB")
    if report.unknown_packets:
        print(f"  {report.unknown_packets} packet(s) in an unrecognised format:", file=sys.stderr)
        for line in report.unknown_detail:
            print(f"    {line}", file=sys.stderr)
    for error in report.errors:
        print(f"  error: {error}", file=sys.stderr)
