"""T039-T042 -- the launcher window.

The project owner chose manual start (spec: Resolved Decisions), accepting that a session
driven before the recorder starts cannot be recovered. That makes three things load-bearing
rather than cosmetic:

* starting must be one action with no command line (FR-025)
* the state must be readable at a glance, in under two seconds (FR-026, SC-010)
* starting late must announce itself, because the missing laps cannot come back (FR-027)

This runs in its own process and only polls the status file. It never touches the socket,
which is what keeps constitution principle II structurally true rather than argued.
"""

from __future__ import annotations

import subprocess
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

from f1dc.capture.status import (
    STATE_ERROR,
    STATE_LISTENING,
    STATE_RECORDING,
    read_status,
)
from f1dc.config import Paths, load_paths
from f1dc.wire.f1_2023 import enums

POLL_MS = 500
RESTART_BACKOFF = 3.0

BG = "#15161a"
FG = "#e8e8ea"
DIM = "#8b8d98"
GREEN = "#3ecf8e"
AMBER = "#e8b339"
RED = "#e5484d"
BLUE = "#5b9dd9"


class LauncherApp:
    def __init__(self, paths: Paths, port: int) -> None:
        self.paths = paths
        self.port = port
        self._proc: subprocess.Popen | None = None
        self._stopping = False
        self._last_restart = 0.0

        self.root = tk.Tk()
        self.root.title("F1 Data Center")
        self.root.configure(bg=BG)
        self.root.geometry("460x300")
        self.root.minsize(420, 280)

        big = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        mid = tkfont.Font(family="Segoe UI", size=12)
        small = tkfont.Font(family="Segoe UI", size=9)

        self.dot = tk.Label(self.root, text="●", font=big, bg=BG, fg=DIM)
        self.dot.pack(pady=(22, 0))

        self.state_label = tk.Label(self.root, text="Starting…", font=big, bg=BG, fg=FG)
        self.state_label.pack()

        self.detail_label = tk.Label(self.root, text="", font=mid, bg=BG, fg=DIM, wraplength=400)
        self.detail_label.pack(pady=(6, 0))

        self.warning_label = tk.Label(
            self.root, text="", font=mid, bg=BG, fg=AMBER, wraplength=400, justify="center"
        )
        self.warning_label.pack(pady=(12, 0))

        self.stats_label = tk.Label(self.root, text="", font=small, bg=BG, fg=DIM)
        self.stats_label.pack(side="bottom", pady=(0, 10))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ process

    def start_recorder(self) -> None:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "f1dc.cli.main",
                "record",
                "--data-dir",
                str(self.paths.data_dir),
                "--port",
                str(self.port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        self._last_restart = time.monotonic()

    def on_close(self) -> None:
        self._stopping = True
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self.root.destroy()

    # ------------------------------------------------------------------ polling

    def poll(self) -> None:
        if self._stopping:
            return

        if self._proc is not None and self._proc.poll() is not None:
            self._handle_exit()
        else:
            self._render(read_status(self.paths.status_path))

        self.root.after(POLL_MS, self.poll)

    def _handle_exit(self) -> None:
        assert self._proc is not None
        code = self._proc.returncode
        stderr = ""
        if self._proc.stderr is not None:
            try:
                stderr = self._proc.stderr.read().decode("utf-8", "replace").strip()
            except (OSError, ValueError):
                pass

        fatal = {
            3: "Another application is already receiving telemetry on this port.",
            4: "The data folder cannot be written to.",
            5: "Not enough free disk space to record safely.",
        }
        if code in fatal:
            self._set(RED, "Not recording", fatal[code], stderr or "")
            return

        # Unexpected death: restart, but not in a tight loop.
        if time.monotonic() - self._last_restart > RESTART_BACKOFF:
            self._set(AMBER, "Restarting…", "The recorder stopped unexpectedly.", "")
            self.start_recorder()
        else:
            self._set(RED, "Not recording", stderr or "The recorder keeps stopping.", "")

    def _render(self, status: dict) -> None:
        state = status.get("state")

        if state == STATE_RECORDING and (session := status.get("session")):
            track = enums.track_name(session.get("track_id", -1))
            stype = enums.session_type_name(session.get("session_type", 0))
            lap = session.get("current_lap", 0)
            detail = f"{track} — {stype}"
            if lap:
                detail += f"   ·   lap {lap}"

            warning = ""
            if session.get("started_late"):
                warning = (
                    "⚠  Recording started mid-session.\n"
                    "The earlier part of this session was not captured."
                )
            if msg := status.get("message"):
                warning = f"{warning}\n{msg}" if warning else f"⚠  {msg}"

            self._set(GREEN, "Recording", detail, warning, status)

        elif state == STATE_LISTENING:
            self._set(
                BLUE,
                "Listening",
                "Waiting for F1 23. Start a session and it will record.",
                status.get("message") or "",
                status,
            )

        elif state == STATE_ERROR:
            self._set(RED, "Not recording", status.get("message") or "", "")

        else:
            self._set(DIM, "Starting…", "", "")

    def _set(
        self,
        colour: str,
        state: str,
        detail: str,
        warning: str,
        status: dict | None = None,
    ) -> None:
        self.dot.configure(fg=colour)
        self.state_label.configure(text=state, fg=FG if colour != RED else RED)
        self.detail_label.configure(text=detail)
        self.warning_label.configure(text=warning, fg=RED if "⚠" in warning else AMBER)

        if status:
            packets = status.get("packets", 0)
            mb = status.get("bytes", 0) / 1e6
            loss = status.get("loss_pct", 0.0)
            free = status.get("free_disk_gb", 0.0)
            n = status.get("sessions_recorded", 0)
            self.stats_label.configure(
                text=(
                    f"{n} session(s)   ·   {packets:,} packets   ·   {mb:,.0f} MB"
                    f"   ·   {loss:.2f}% lost   ·   {free:,.0f} GB free"
                )
            )

    def run(self) -> int:
        self.start_recorder()
        self.root.after(POLL_MS, self.poll)
        self.root.mainloop()
        return 0


def main(data_dir: str | None = None, port: int = 20777) -> int:
    paths = load_paths(data_dir)
    return LauncherApp(paths, port).run()


if __name__ == "__main__":
    raise SystemExit(main())
