"""Packet-loss measurement that does not depend on the send rate (FR-003).

**Why the first version was wrong.** It counted gaps in ``frameIdentifier`` as lost frames.
But that counter numbers the game's *own* frames, and at the 60 Hz send rate the game
simply does not send every one: a game running at ~67 fps skips roughly one frame number
in ten. Real captures showed tens of thousands of regular one-frame skips, so sessions with
**zero** real loss reported 5-18%, and 15 of 35 sessions were wrongly marked incomplete in
the library. The original calibration run at the 120 Hz setting sent nearly every frame,
which is why the flaw did not show up then.

**What is measured now.** Every frame the game sends arrives as three datagrams --
LapData, Motion and CarTelemetry, consecutively and with the same frame number. So:

* a frame that arrives with fewer than three of them lost datagrams in transit;
* a gap in frame numbers far larger than the game's normal skips is a burst in which whole
  frames were lost. It is scaled by the session's measured send ratio, because not every
  frame number in the gap would have been sent anyway.

Across ~1.27 million frames from the six worst-reporting sessions, exactly one arrived
incomplete -- the recorder is lossless in practice -- while the burst rule still catches
the 79-frame hole in the reference capture.

Standard library only: this runs inside the recorder (constitution principle II), and
ingest reuses it so the live figure and the stored figure cannot disagree.
"""

from __future__ import annotations

#: The three packets the game sends together for every frame it sends.
TRACKED_PACKETS = frozenset({0, 2, 6})
DATAGRAMS_PER_FRAME = len(TRACKED_PACKETS)

#: A gap in frame numbers larger than this is a burst of loss, not a send-rate skip.
#: At a 60 Hz send rate the game skips 1-3 frame numbers between sends even at 240 fps.
BURST_GAP_FRAMES = 5


class LossMeter:
    """Fed every (packet_id, frame) of one session, in arrival order."""

    __slots__ = (
        "_count",
        "_current",
        "burst_frames",
        "first_frame",
        "frames_seen",
        "last_frame",
        "missing_datagrams",
    )

    def __init__(self) -> None:
        self.first_frame: int | None = None
        self.last_frame: int | None = None
        self.frames_seen = 0
        self.missing_datagrams = 0
        self.burst_frames = 0
        self._current: int | None = None
        self._count = 0

    def observe(self, packet_id: int, frame: int) -> None:
        """Call for packets that carry a frame counter (``PacketHeader.has_frame_counter``)."""
        if packet_id not in TRACKED_PACKETS:
            return
        if frame == self._current:
            self._count += 1
            return

        if self._current is not None:
            self.missing_datagrams += max(0, DATAGRAMS_PER_FRAME - self._count)
            if frame > self._current + BURST_GAP_FRAMES:
                self.burst_frames += frame - self._current - 1

        self._current = frame
        self._count = 1
        self.frames_seen += 1
        if self.first_frame is None:
            self.first_frame = frame
        self.last_frame = frame if self.last_frame is None else max(self.last_frame, frame)

    @property
    def send_ratio(self) -> float:
        """Fraction of frame numbers the game sends, measured outside bursts.

        The bursts must be excluded from the span: otherwise a hole in the data lowers the
        apparent send rate, and the hole is then under-counted by that same lowered rate.
        """
        if self.first_frame is None or self.last_frame is None:
            return 1.0
        span = self.last_frame - self.first_frame + 1 - self.burst_frames
        return min(1.0, self.frames_seen / span) if span > 0 else 1.0

    @property
    def frames_lost(self) -> float:
        """Frames' worth of data lost: incomplete frames plus scaled bursts."""
        return self.missing_datagrams / DATAGRAMS_PER_FRAME + self.burst_frames * self.send_ratio

    @property
    def loss_pct(self) -> float:
        lost = self.frames_lost
        expected = self.frames_seen + self.burst_frames * self.send_ratio
        return 100.0 * lost / expected if expected > 0 else 0.0
