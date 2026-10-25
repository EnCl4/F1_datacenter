"""T055, T058 -- ingest orchestration.

Idempotent by construction (FR-015, constitution principle VII): each session is written
to a temporary directory and renamed into place. A failed run leaves nothing half-written,
and a repeated run produces identical bytes because the inputs and the code are the same.

Runs in its own process. It never executes inside the recorder.
"""

from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from f1dc.capture.rawlog import iter_records
from f1dc.config import Paths
from f1dc.ingest import INGEST_VERSION
from f1dc.ingest.compress import compress_log, is_compressed, open_raw
from f1dc.ingest.laps import build
from f1dc.ingest.sessionizer import RawSession, Sessionizer
from f1dc.ingest.traces import to_rows
from f1dc.models import Recording
from f1dc.store import catalog, layout
from f1dc.store.lock import WriteLockBusy, write_lock
from f1dc.store.schema import (
    EVENT_SCHEMA,
    EXCURSION_SCHEMA,
    FIELD_LAPS_SCHEMA,
    FIELD_SCHEMA,
    LAP_CAR_SCHEMA,
    LAP_SCHEMA,
    RECORDING_SCHEMA,
    SESSION_SCHEMA,
    STINT_SCHEMA,
    TIMELINE_SCHEMA,
    TRACE_SCHEMA,
    TYRE_SET_SCHEMA,
    table_from_rows,
)

log = logging.getLogger("f1dc.ingest")

EXIT_OK = 0
EXIT_UNKNOWN_FORMAT = 6
EXIT_NO_LOGS = 7
EXIT_BUSY = 8


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
        result.traces = build_traces(raw, result)
        result.tables = car_tables(raw, result.session.session_uid, result.stints)
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


def build_traces(raw: RawSession, result) -> dict[str, list] | None:
    """Per-metre traces for every lap with channel data (feature 002).

    The finish anchor uses the lap time feature 001 already established, from
    SessionHistory, so the running time gap at the line matches the official lap times.
    """
    lap_times = {lap.lap_number: lap.lap_time_ms for lap in result.laps}
    track_length = result.session.track_length_m
    merged: dict[str, list] | None = None
    for number in raw.traces.lap_numbers():
        trace = raw.traces.build(number, track_length, lap_times.get(number))
        if trace is None:
            continue
        columns = to_rows(result.session.session_uid, number, trace)
        if merged is None:
            merged = columns
        else:
            for name, values in columns.items():
                merged[name].extend(values)
    return merged


def car_tables(raw: RawSession, uid: str, player_stints: list | None = None) -> dict:
    """Feature 003 tables for one session (data-model.md)."""
    car = raw.car
    cars, field_laps = car.field_rows(uid, raw.player_index, player_stints)
    return {
        layout.LAP_CAR_FILE: (car.lap_rows(uid), LAP_CAR_SCHEMA),
        layout.EXCURSIONS_FILE: (car.excursion_rows(uid), EXCURSION_SCHEMA),
        layout.FIELD_FILE: (cars, FIELD_SCHEMA),
        layout.FIELD_LAPS_FILE: (field_laps, FIELD_LAPS_SCHEMA),
        layout.TIMELINE_FILE: (car.timeline_rows(uid), TIMELINE_SCHEMA),
        layout.EVENTS_FILE: (car.event_rows(uid), EVENT_SCHEMA),
        layout.TYRE_SETS_FILE: (car.tyre_set_rows(uid), TYRE_SET_SCHEMA),
    }


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
    if result.traces is not None:
        pq.write_table(
            pa.Table.from_pydict(result.traces, schema=TRACE_SCHEMA),
            temp / layout.TRACES_FILE,
            compression="zstd",
        )
    for filename, (rows, schema) in result.tables.items():
        pq.write_table(table_from_rows(rows, schema), temp / filename, compression="zstd")
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

    # Shared with session deletion (feature 003, FR-031): the two never interleave.
    try:
        with write_lock(paths, "ingest") as lock:
            _ingest_all(paths, logs, stored, report, lock=lock, force=force,
                        explicit=explicit, compress_logs=compress_logs)
    except WriteLockBusy as exc:
        print(f"another writer is busy ({exc.holder}); try again shortly", file=sys.stderr)
        return EXIT_BUSY

    _print_report(report)
    return report.exit_code


def _ingest_all(paths, logs, stored, report, *, lock, force, explicit, compress_logs) -> None:
    for log_path in logs:
        lock.refresh()  # an hour-long ingest must not look like a stale lock
        if not log_path.exists():
            report.errors.append(f"{log_path} does not exist")
            continue

        if not force and not explicit and _already_current(log_path, stored):
            report.sessions_skipped += 1
            continue

        try:
            ingest_log(paths, log_path, report=report)
            report.logs_processed += 1
        except Exception as exc:  # one bad log must not stop the rest
            log.exception("failed to ingest %s", log_path.name)
            report.errors.append(f"{log_path.name}: {exc}")
            continue

        if compress_logs and not is_compressed(log_path):
            before = log_path.stat().st_size
            try:
                after_path = compress_log(log_path)
                report.compressed_bytes_saved += before - after_path.stat().st_size
            except OSError as exc:
                report.errors.append(f"{log_path.name}: compression failed, original kept ({exc})")


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
