"""T031-T037 -- the headless recorder.

Constitution principle II: this is the only component whose failure loses data
permanently, so the receive loop does exactly two things -- ``recv`` and ``put`` on a
queue. A separate writer thread owns the disk; a separate status thread owns reporting.
No parsing, no database, no compression, no UI.

The four header fields read on the receive path (sessionUID, packetId, frameIdentifier,
overallFrameIdentifier) decide which file a datagram belongs to and whether frames were
lost. That is routing, not interpretation.
"""

from __future__ import annotations

import logging
import queue
import shutil
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from f1dc.capture.rawlog import RawLogWriter
from f1dc.capture.status import (
    STATE_ERROR,
    STATE_LISTENING,
    STATE_RECORDING,
    RecorderStatus,
    SessionStatus,
    clear_status,
    write_status,
)
from f1dc.wire.header import HEADER, HEADER_SIZE

log = logging.getLogger("f1dc.capture")

DEFAULT_PORT = 20777
RECV_BUFFER = 4096
SOCKET_TIMEOUT = 0.5
QUEUE_MAXSIZE = 16384
STATUS_INTERVAL = 0.5

#: Exit codes, per contracts/cli.md.
EXIT_OK = 0
EXIT_PORT_IN_USE = 3
EXIT_DATA_DIR = 4
EXIT_DISK_SPACE = 5

MIN_FREE_BYTES = 5 * 1024**3
WARN_FREE_BYTES = 15 * 1024**3

#: Packet id whose frame identifiers are counted for the loss metric. LapData is sent at
#: the configured send rate, so gaps in it are gaps in the stream.
LOSS_REFERENCE_PACKET = 2

#: A session whose first observed lap is beyond this, or whose session clock is already
#: past LATE_START_SECONDS, was already running when we started (FR-027).
LATE_START_LAP = 1
LATE_START_SECONDS = 30.0

#: Offsets within the 50-byte LapData per-car item.
_LAPDATA_ITEM_SIZE = 50
_LAPDATA_CURRENT_LAP_OFFSET = 31


class PortInUseError(Exception):
    """Another application is already listening on the telemetry port (FR-006)."""


class InsufficientDiskError(Exception):
    """Not enough free space to start safely (FR-005)."""


@dataclass
class SessionRecord:
    """Bookkeeping for one recorded session."""

    session_uid: int
    path: Path
    started_at: float
    packets: int = 0
    bytes: int = 0
    first_frame: int | None = None
    last_frame: int | None = None
    frames_lost: int = 0
    started_late: bool = False
    current_lap: int = 0
    track_id: int = -1
    session_type: int = 0
    menu_records: int = 0

    @property
    def frames_expected(self) -> int:
        if self.first_frame is None or self.last_frame is None:
            return 0
        return max(0, self.last_frame - self.first_frame + 1)

    @property
    def loss_pct(self) -> float:
        expected = self.frames_expected
        if expected <= 0:
            return 0.0
        return 100.0 * self.frames_lost / expected


@dataclass
class RecorderResult:
    exit_code: int = EXIT_OK
    sessions: list[SessionRecord] = field(default_factory=list)
    message: str | None = None


class Recorder:
    """Captures the telemetry stream to raw logs. One process, three threads."""

    def __init__(
        self,
        raw_dir: Path,
        status_path: Path,
        *,
        port: int = DEFAULT_PORT,
        host: str = "0.0.0.0",
        queue_maxsize: int = QUEUE_MAXSIZE,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.status_path = Path(status_path)
        self.port = port
        self.host = host

        self._queue: queue.Queue[tuple[bytes, float] | None] = queue.Queue(queue_maxsize)
        self._stop = threading.Event()
        self._sock: socket.socket | None = None

        self.sessions: list[SessionRecord] = []
        self.current: SessionRecord | None = None
        self._writer: RawLogWriter | None = None
        self._started_at = time.time()

        self.queue_high_water = 0
        self.dropped_by_backpressure = 0
        self.total_packets = 0
        self.total_bytes = 0

    # ---------------------------------------------------------------- preflight

    def preflight(self) -> None:
        """Fail fast and clearly, before the driver thinks they are recording."""
        try:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            probe = self.raw_dir / ".write-probe"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError as exc:
            raise OSError(f"raw directory {self.raw_dir} is not writable: {exc}") from exc

        free = shutil.disk_usage(self.raw_dir).free
        if free < MIN_FREE_BYTES:
            raise InsufficientDiskError(
                f"only {free / 1024**3:.1f} GB free on {self.raw_dir.drive or self.raw_dir}; "
                f"capture needs at least {MIN_FREE_BYTES / 1024**3:.0f} GB "
                f"(telemetry writes about 1.3 GB per hour)"
            )

    def _bind(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        except OSError:
            pass  # best effort; a smaller kernel buffer still works
        try:
            sock.bind((self.host, self.port))
        except OSError as exc:
            sock.close()
            raise PortInUseError(
                f"cannot listen on UDP {self.host}:{self.port} -- another application is "
                f"probably already receiving telemetry (a dashboard, or a second "
                f"recorder). Close it, or enable UDP Broadcast Mode in the game."
            ) from exc
        sock.settimeout(SOCKET_TIMEOUT)
        return sock

    # ---------------------------------------------------------------- lifecycle

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> RecorderResult:
        """Block until stopped. Returns a summary of what was captured."""
        try:
            self.preflight()
        except InsufficientDiskError as exc:
            write_status(self.status_path, RecorderStatus(state=STATE_ERROR, message=str(exc)))
            return RecorderResult(EXIT_DISK_SPACE, message=str(exc))
        except OSError as exc:
            write_status(self.status_path, RecorderStatus(state=STATE_ERROR, message=str(exc)))
            return RecorderResult(EXIT_DATA_DIR, message=str(exc))

        try:
            self._sock = self._bind()
        except PortInUseError as exc:
            write_status(self.status_path, RecorderStatus(state=STATE_ERROR, message=str(exc)))
            return RecorderResult(EXIT_PORT_IN_USE, message=str(exc))

        self._started_at = time.time()
        writer_thread = threading.Thread(target=self._writer_loop, name="f1dc-writer", daemon=True)
        status_thread = threading.Thread(target=self._status_loop, name="f1dc-status", daemon=True)
        writer_thread.start()
        status_thread.start()

        try:
            self._receive_loop()
        finally:
            self._queue.put(None)
            writer_thread.join(timeout=10)
            self._stop.set()
            status_thread.join(timeout=2)
            if self._sock is not None:
                self._sock.close()
            self._close_session()
            clear_status(self.status_path)

        return RecorderResult(EXIT_OK, sessions=self.sessions)

    # ---------------------------------------------------------------- the hot path

    def _receive_loop(self) -> None:
        """The capture path. Nothing but recv and put belongs in here."""
        assert self._sock is not None
        monotonic = time.monotonic
        base = monotonic()
        put = self._queue.put_nowait

        while not self._stop.is_set():
            try:
                data = self._sock.recv(RECV_BUFFER)
            except TimeoutError:
                continue
            except OSError:
                log.debug("socket closed, ending receive loop")
                break
            try:
                put((data, monotonic() - base))
            except queue.Full:
                # Backpressure is reportable data loss, never silent.
                self.dropped_by_backpressure += 1

    # ---------------------------------------------------------------- writer thread

    def _writer_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            payload, timestamp = item
            depth = self._queue.qsize()
            if depth > self.queue_high_water:
                self.queue_high_water = depth
            try:
                self._handle(payload, timestamp)
            except OSError:
                # A disk failure mid-session: stop cleanly so what was captured survives.
                log.exception("writer failed; stopping capture")
                self._stop.set()
                return

    def _handle(self, payload: bytes, timestamp: float) -> None:
        if len(payload) < HEADER_SIZE:
            return

        (
            _fmt,
            _year,
            _major,
            _minor,
            _pver,
            packet_id,
            session_uid,
            session_time,
            frame_id,
            overall_frame,
            player_index,
            _secondary,
        ) = HEADER.unpack_from(payload)

        if session_uid == 0:
            # Menu traffic belongs to whatever file is open; ingest discards it (FR-007).
            if self._writer is not None and self.current is not None:
                self._writer.write(payload, timestamp)
                self.current.menu_records += 1
                self.total_packets += 1
                self.total_bytes += len(payload)
            return

        if self.current is None or self.current.session_uid != session_uid:
            self._close_session()
            self._open_session(session_uid, session_time)

        assert self._writer is not None and self.current is not None
        self._writer.write(payload, timestamp)
        self.current.packets += 1
        self.current.bytes += len(payload)
        self.total_packets += 1
        self.total_bytes += len(payload)

        has_frame = not (frame_id == 0 and overall_frame == 0)
        if packet_id == LOSS_REFERENCE_PACKET and has_frame:
            self._account_frames(frame_id)
            self._track_lap(payload, player_index, session_time)
        elif packet_id == 1:
            self._track_session_meta(payload)

    def _account_frames(self, frame_id: int) -> None:
        """Count gaps in the reference packet's frame identifiers (FR-003).

        Packets whose frame counters are zeroed -- which the game does for the packets it
        sends as a session closes -- are excluded by the caller. Counting them would
        report a phantom loss of every frame in the session.
        """
        cur = self.current
        assert cur is not None
        if cur.first_frame is None:
            cur.first_frame = frame_id
        elif cur.last_frame is not None and frame_id > cur.last_frame + 1:
            cur.frames_lost += frame_id - cur.last_frame - 1
        cur.last_frame = frame_id

    def _track_lap(self, payload: bytes, player_index: int, session_time: float) -> None:
        cur = self.current
        assert cur is not None
        offset = HEADER_SIZE + player_index * _LAPDATA_ITEM_SIZE + _LAPDATA_CURRENT_LAP_OFFSET
        if offset >= len(payload):
            return
        lap = payload[offset]
        if cur.current_lap == 0:
            # First lap we ever see for this session decides whether we started late.
            cur.started_late = lap > LATE_START_LAP or session_time > LATE_START_SECONDS
        cur.current_lap = lap

    def _track_session_meta(self, payload: bytes) -> None:
        """Two bytes so the launcher can name the circuit. Not interpretation."""
        cur = self.current
        assert cur is not None
        if len(payload) >= HEADER_SIZE + 8:
            cur.session_type = payload[HEADER_SIZE + 6]
            cur.track_id = int.from_bytes(payload[HEADER_SIZE + 7 : HEADER_SIZE + 8], "little",
                                          signed=True)

    # ---------------------------------------------------------------- session files

    def _open_session(self, session_uid: int, session_time: float) -> None:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
        path = self.raw_dir / f"{stamp}_{session_uid}.f1raw"
        writer = RawLogWriter(path, self.port)
        writer.open()
        self._writer = writer
        self.current = SessionRecord(
            session_uid=session_uid, path=path, started_at=time.time()
        )
        self.sessions.append(self.current)

    def _close_session(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        self.current = None

    # ---------------------------------------------------------------- status thread

    def _status_loop(self) -> None:
        while not self._stop.is_set():
            write_status(self.status_path, self.snapshot())
            self._stop.wait(STATUS_INTERVAL)

    def snapshot(self) -> RecorderStatus:
        cur = self.current
        session = None
        state = STATE_LISTENING
        if cur is not None:
            state = STATE_RECORDING
            session = SessionStatus(
                uid=str(cur.session_uid),
                track_id=cur.track_id,
                session_type=cur.session_type,
                current_lap=cur.current_lap,
                started_late=cur.started_late,
            )

        try:
            free = shutil.disk_usage(self.raw_dir).free
        except OSError:
            free = 0

        message = None
        if self.dropped_by_backpressure:
            message = (
                f"{self.dropped_by_backpressure} packet(s) dropped: the disk could not "
                f"keep up with the telemetry stream"
            )
        elif 0 < free < WARN_FREE_BYTES:
            message = f"only {free / 1024**3:.1f} GB free; about {free / 1.3e9:.1f} hours left"

        return RecorderStatus(
            state=state,
            since=self._started_at,
            session=session,
            packets=self.total_packets,
            bytes=self.total_bytes,
            loss_pct=round(cur.loss_pct, 4) if cur else 0.0,
            queue_high_water=self.queue_high_water,
            free_disk_gb=round(free / 1024**3, 1),
            sessions_recorded=len(self.sessions),
            message=message,
        )
