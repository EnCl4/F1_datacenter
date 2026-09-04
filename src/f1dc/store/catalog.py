"""T057 -- the read side: DuckDB views over the Parquet files.

The plan called for a persistent ``catalog.duckdb``. Implementation simplified it to an
**in-memory** connection whose views point at the Parquet glob, created per query. That
is strictly better for the property the plan actually wanted: with no database file there
is no single-writer lock to contend with at all, and the derived store stays fully
described by the Parquet files on disk.

Starred recordings are the one piece of mutable user state. They live in a small JSON
file that ingest never writes, so starring a session cannot make ingest non-idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from f1dc.config import Paths
from f1dc.store import layout

SESSION_VIEW = "sessions"
LAP_VIEW = "laps"
STINT_VIEW = "stints"


def has_data(paths: Paths) -> bool:
    return any(layout.iter_session_dirs(paths))


def connect(paths: Paths) -> duckdb.DuckDBPyConnection:
    """In-memory connection with views over the derived Parquet files."""
    con = duckdb.connect(":memory:")
    if not has_data(paths):
        return con
    con.execute(
        f"CREATE VIEW {SESSION_VIEW} AS "
        f"SELECT * FROM read_parquet('{layout.session_glob(paths, layout.SESSION_FILE)}')"
    )
    con.execute(
        f"CREATE VIEW {LAP_VIEW} AS "
        f"SELECT * FROM read_parquet('{layout.session_glob(paths, layout.LAPS_FILE)}')"
    )
    con.execute(
        f"CREATE VIEW {STINT_VIEW} AS "
        f"SELECT * FROM read_parquet('{layout.session_glob(paths, layout.STINTS_FILE)}', "
        f"union_by_name=true)"
    )
    return con


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    cursor = con.execute(sql, params or [])
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------- starred


def get_starred(paths: Paths) -> set[str]:
    path = layout.starred_path(paths)
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return set()


def set_starred(paths: Paths, session_uid: str, starred: bool) -> None:
    current = get_starred(paths)
    if starred:
        current.add(session_uid)
    else:
        current.discard(session_uid)
    path = layout.starred_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(current), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------- queries


def list_sessions(
    paths: Paths,
    *,
    track_id: int | None = None,
    session_category: str | None = None,
    session_type: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_abandoned: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """The library list. Ordered most recent first (FR-018)."""
    if not has_data(paths):
        return 0, []

    where: list[str] = []
    params: list[Any] = []
    if track_id is not None:
        where.append("track_id = ?")
        params.append(track_id)
    if session_category:
        where.append("session_category = ?")
        params.append(session_category)
    if session_type is not None:
        where.append("session_type = ?")
        params.append(session_type)
    if date_from:
        where.append("started_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("started_at <= ?")
        params.append(date_to + "T23:59:59")
    if not include_abandoned:
        where.append("ended_naturally")

    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with connect(paths) as con:
        total = con.execute(
            f"SELECT count(*) FROM {SESSION_VIEW} {clause}", params
        ).fetchone()[0]
        items = _rows(
            con,
            f"SELECT * FROM {SESSION_VIEW} {clause} "
            f"ORDER BY started_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )

    starred = get_starred(paths)
    for item in items:
        item["starred"] = item["session_uid"] in starred
    return total, items


def get_session(paths: Paths, session_uid: str) -> dict[str, Any] | None:
    if not has_data(paths):
        return None
    with connect(paths) as con:
        rows = _rows(
            con, f"SELECT * FROM {SESSION_VIEW} WHERE session_uid = ?", [session_uid]
        )
    if not rows:
        return None
    session = rows[0]
    session["starred"] = session_uid in get_starred(paths)
    return session


def get_laps(paths: Paths, session_uid: str) -> list[dict[str, Any]]:
    """Every lap, including those that do not count.

    Returning all of them with ``counts`` and ``exclusion_reason`` attached -- rather than
    a pre-filtered list -- is what keeps the validity rule in exactly one place
    (constitution principle VI).
    """
    if not has_data(paths):
        return []
    with connect(paths) as con:
        return _rows(
            con,
            f"SELECT * FROM {LAP_VIEW} WHERE session_uid = ? ORDER BY lap_number",
            [session_uid],
        )


def get_stints(paths: Paths, session_uid: str) -> list[dict[str, Any]]:
    if not has_data(paths):
        return []
    with connect(paths) as con:
        try:
            return _rows(
                con,
                f"SELECT * FROM {STINT_VIEW} WHERE session_uid = ? ORDER BY stint_index",
                [session_uid],
            )
        except duckdb.Error:
            return []


def list_tracks(paths: Paths) -> list[dict[str, Any]]:
    if not has_data(paths):
        return []
    with connect(paths) as con:
        return _rows(
            con,
            f"SELECT track_id, any_value(track_name) AS track_name, "
            f"count(*) AS session_count FROM {SESSION_VIEW} "
            f"GROUP BY track_id ORDER BY track_name",
        )


def session_count(paths: Paths) -> int:
    if not has_data(paths):
        return 0
    with connect(paths) as con:
        return con.execute(f"SELECT count(*) FROM {SESSION_VIEW}").fetchone()[0]


def stored_ingest_versions(paths: Paths) -> dict[str, str]:
    """Session uid -> the ingest version that produced it, for `--all` to skip current ones."""
    versions: dict[str, str] = {}
    for directory in layout.iter_session_dirs(paths):
        parquet = directory / layout.SESSION_FILE
        if not parquet.exists():
            continue
        try:
            with duckdb.connect(":memory:") as con:
                row = con.execute(
                    f"SELECT ingest_version FROM read_parquet('{parquet.as_posix()}') LIMIT 1"
                ).fetchone()
            if row:
                versions[directory.name] = row[0]
        except duckdb.Error:
            continue
    return versions


def find_path(paths: Paths, session_uid: str) -> Path:
    return layout.session_dir(paths, session_uid)
