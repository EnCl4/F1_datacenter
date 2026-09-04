"""Shared test fixtures.

Two tiers, per research R11:

* ``calibration_slice.f1raw`` -- committed, ~3.4 MB, real bytes from a real race. Runs on
  every change and is what constitution principle IV requires.
* The full 229 MB capture -- local only, referenced by ``--raw``. Tests needing it are
  marked ``needs_full_capture`` and skip cleanly when it is absent.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from f1dc.capture.rawlog import Record, iter_records
from f1dc.wire.header import PacketHeader, decode_header

FIXTURE = Path(__file__).parent / "fixtures" / "calibration_slice.f1raw"

# Ground truth for the reference capture: Interlagos, 5-lap race, 2026-09-04.
REFERENCE = {
    "track_id": 16,
    "track_name": "Interlagos",
    "session_type": 10,
    "session_category": "race",
    "total_laps": 5,
    "track_length": 4294,
    "weather": 2,  # overcast
    "track_temperature": 31,
    "air_temperature": 24,
    "ai_difficulty": 90,
    "player_car_index": 19,
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--raw",
        action="store",
        default=None,
        help="Path to the full calibration capture for end-to-end tests.",
    )


@pytest.fixture(scope="session")
def fixture_path() -> Path:
    if not FIXTURE.exists():
        pytest.fail(
            f"missing test fixture {FIXTURE}.\n"
            f"Rebuild it with:\n"
            f"  python tools/build_fixture.py <capture.bin> {FIXTURE} --legacy-probe"
        )
    return FIXTURE


@pytest.fixture(scope="session")
def records(fixture_path: Path) -> list[Record]:
    return list(iter_records(fixture_path))


@pytest.fixture(scope="session")
def by_packet_id(records: list[Record]) -> dict[int, list[Record]]:
    """Session-scoped index of records by packet id, excluding menu-state traffic."""
    grouped: dict[int, list[Record]] = defaultdict(list)
    for rec in records:
        header = decode_header(rec.payload)
        if header.session_uid == 0:
            continue
        grouped[header.packet_id].append(rec)
    return dict(grouped)


@pytest.fixture(scope="session")
def player_index(by_packet_id: dict[int, list[Record]]) -> int:
    return decode_header(by_packet_id[1][0].payload).player_car_index


#: The synthetic capture filename ingest parses timestamps out of.
FIXTURE_LOG_NAME = "2026-09-04T11-04-12_15975277775803518192.f1raw"
REFERENCE_UID = "15975277775803518192"

#: Ground-truth lap times for the reference race, from SessionHistory.
REFERENCE_LAPS = {1: 76859, 2: 71439, 3: 79146, 4: 90600, 5: 72642}


@pytest.fixture(scope="session")
def ingested(tmp_path_factory, fixture_path: Path):
    """A derived store built from the committed fixture.

    Note the fixture is deliberately subsampled, so its measured packet loss is very high.
    That is honest -- frames really are missing from it -- so tests assert on lap content
    rather than on loss figures.
    """
    import shutil

    from f1dc.config import Paths
    from f1dc.ingest.pipeline import run_ingest

    root = tmp_path_factory.mktemp("derived-store")
    paths = Paths(root)
    paths.ensure()
    shutil.copy(fixture_path, paths.raw_dir / FIXTURE_LOG_NAME)
    run_ingest(paths, compress_logs=False)
    return paths


def first_of(by_packet_id: dict[int, list[Record]], packet_id: int) -> bytes:
    payloads = by_packet_id.get(packet_id)
    if not payloads:
        pytest.skip(f"fixture contains no packet id {packet_id}")
    return payloads[0].payload


def headers(records: list[Record]) -> list[PacketHeader]:
    return [decode_header(r.payload) for r in records]
