"""T038 -- the f1dc command line.

The driver is never required to use this: FR-025 demands a desktop shortcut and no
command line for normal use. But every action must be reachable from here, for testing
and for recovery.

Sub-command modules are imported lazily so that `f1dc record` -- the one command that
matters when data is on the line -- does not pull in pyarrow, duckdb or fastapi.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from f1dc.config import ConfigError, load_paths

EXIT_USAGE = 2


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", type=Path, default=None, help="override the data directory")
    parser.add_argument(
        "--allow-sync-root",
        action="store_true",
        help="permit a cloud-synced data directory (strongly discouraged)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="f1dc", description="F1 Data Center")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="show diagnostic logging; repeat for debug detail",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_record = sub.add_parser("record", help="capture telemetry until stopped")
    _add_common(p_record)
    p_record.add_argument("--port", type=int, default=20777)
    p_record.add_argument("--host", default="0.0.0.0")
    p_record.add_argument("--status-file", type=Path, default=None)

    p_launch = sub.add_parser("launch", help="open the recorder window")
    _add_common(p_launch)
    p_launch.add_argument("--port", type=int, default=20777)

    p_ingest = sub.add_parser("ingest", help="interpret raw logs into the derived store")
    _add_common(p_ingest)
    p_ingest.add_argument("paths", nargs="*", type=Path, help="raw logs; default is all new ones")
    p_ingest.add_argument("--all", action="store_true", help="every raw log found")
    p_ingest.add_argument("--force", action="store_true", help="re-ingest even if current")
    p_ingest.add_argument("--no-compress", action="store_true", help="skip zstd compression")

    p_serve = sub.add_parser("serve", help="run the local read-only web app")
    _add_common(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8420)
    p_serve.add_argument("--open", action="store_true", help="open a browser")

    p_doctor = sub.add_parser("doctor", help="diagnose the setup")
    _add_common(p_doctor)
    p_doctor.add_argument("--port", type=int, default=20777)
    p_doctor.add_argument("--listen-seconds", type=float, default=10.0)

    p_prune = sub.add_parser("prune", help="delete raw logs past the retention window")
    _add_common(p_prune)
    p_prune.add_argument("--older-than", default="90d")
    p_prune.add_argument("--dry-run", action="store_true")
    p_prune.add_argument("--yes", action="store_true")

    p_star = sub.add_parser("star", help="keep a session's raw log permanently")
    _add_common(p_star)
    p_star.add_argument("session_uid")
    p_star.add_argument("--remove", action="store_true")

    return parser


def cmd_record(args: argparse.Namespace) -> int:
    from f1dc.capture.recorder import Recorder

    paths = load_paths(args.data_dir, allow_sync_root=args.allow_sync_root)
    recorder = Recorder(
        paths.raw_dir,
        args.status_file or paths.status_path,
        port=args.port,
        host=args.host,
    )

    def handle(_sig: int, _frame: object) -> None:
        recorder.stop()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    print(f"listening on {args.host}:{args.port} -> {paths.raw_dir}", flush=True)
    result = recorder.run()

    if result.message:
        print(result.message, file=sys.stderr)
    for session in result.sessions:
        print(
            f"  {session.path.name}: {session.packets} packets, "
            f"{session.bytes / 1e6:.1f} MB, {session.loss_pct:.3f}% lost"
            + ("  [started late]" if session.started_late else "")
        )
    return result.exit_code


def cmd_launch(args: argparse.Namespace) -> int:
    from f1dc.launcher.app import main as launcher_main

    return launcher_main(args.data_dir, args.port)


def cmd_ingest(args: argparse.Namespace) -> int:
    from f1dc.ingest.pipeline import run_ingest

    paths = load_paths(args.data_dir, allow_sync_root=args.allow_sync_root)
    return run_ingest(
        paths,
        explicit=args.paths or None,
        force=args.force,
        compress_logs=not args.no_compress,
    )


def cmd_serve(args: argparse.Namespace) -> int:
    from f1dc.api.main import serve

    paths = load_paths(args.data_dir, allow_sync_root=args.allow_sync_root)
    return serve(paths, host=args.host, port=args.port, open_browser=args.open)


def cmd_doctor(args: argparse.Namespace) -> int:
    from f1dc.cli.doctor import run_doctor

    return run_doctor(
        args.data_dir,
        port=args.port,
        listen_seconds=args.listen_seconds,
        allow_sync_root=args.allow_sync_root,
    )


def cmd_prune(args: argparse.Namespace) -> int:
    from f1dc.cli.prune import run_prune

    paths = load_paths(args.data_dir, allow_sync_root=args.allow_sync_root)
    return run_prune(paths, args.older_than, dry_run=args.dry_run, assume_yes=args.yes)


def cmd_star(args: argparse.Namespace) -> int:
    from f1dc.store.catalog import set_starred

    paths = load_paths(args.data_dir, allow_sync_root=args.allow_sync_root)
    starred = not args.remove
    set_starred(paths, args.session_uid, starred)
    print(f"session {args.session_uid} {'starred' if starred else 'unstarred'}")
    return 0


COMMANDS = {
    "record": cmd_record,
    "launch": cmd_launch,
    "ingest": cmd_ingest,
    "serve": cmd_serve,
    "doctor": cmd_doctor,
    "prune": cmd_prune,
    "star": cmd_star,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level={0: logging.WARNING, 1: logging.INFO}.get(args.verbose, logging.DEBUG),
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return COMMANDS[args.command](args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
