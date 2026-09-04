"""T044 -- session boundaries, menu-state discard and end classification."""

from __future__ import annotations

from datetime import UTC, datetime

from f1dc.capture.rawlog import iter_records
from f1dc.ingest.sessionizer import Sessionizer, scan
from f1dc.store import catalog
from tests.conftest import REFERENCE_UID


def sessions_from(fixture_path):
    return scan(iter_records(fixture_path), datetime(2026, 9, 4, 11, 4, 12, tzinfo=UTC))


def test_one_real_session_is_found(fixture_path) -> None:
    sessions = sessions_from(fixture_path)
    assert len(sessions) == 1
    assert str(sessions[0].session_uid) == REFERENCE_UID


def test_menu_state_is_discarded_not_turned_into_a_session(fixture_path) -> None:
    """FR-007. The reference capture contains 14 Event packets with sessionUID == 0;
    without this rule they would appear in the library as a phantom session."""
    sessionizer = Sessionizer(datetime(2026, 9, 4, tzinfo=UTC))
    sessionizer.feed(iter_records(fixture_path))
    assert sessionizer.menu_records == 14
    assert all(s.session_uid != 0 for s in sessionizer.result())


def test_deliberately_undecoded_packets_are_not_reported_as_unknown(fixture_path) -> None:
    """Motion, Participants, CarTelemetry and MotionEx are declared, not unrecognised.

    Counting them under FR-017 would make every single ingest exit non-zero and cry wolf
    about a format problem that does not exist.
    """
    sessionizer = Sessionizer(datetime(2026, 9, 4, tzinfo=UTC))
    sessionizer.feed(iter_records(fixture_path))
    assert sum(sessionizer.unknown.values()) == 0, dict(sessionizer.unknown)
    assert set(sessionizer.declared_undecoded) == {0, 4, 6, 13}


def test_the_race_ended_at_the_chequered_flag(fixture_path) -> None:
    session = sessions_from(fixture_path)[0]
    assert session.end_reason == "chequered"
    assert session.ended_naturally is True


def test_an_abandoned_session_is_distinguishable(fixture_path) -> None:
    """FR-014: a session with laps but no end event did not finish."""
    session = sessions_from(fixture_path)[0]
    session.classification = None
    session.events = [e for e in session.events if e not in ("CHQF", "SEND")]
    assert session.end_reason == "abandoned"
    assert session.ended_naturally is False


def test_a_session_with_nothing_in_it_reads_as_interrupted(fixture_path) -> None:
    session = sessions_from(fixture_path)[0]
    session.classification = None
    session.events = []
    session.laps = {}
    assert session.end_reason == "interrupted"


def test_session_metadata_matches_the_reference_race(fixture_path) -> None:
    data = sessions_from(fixture_path)[0].session_data
    assert data is not None
    assert data.track_name == "Interlagos"
    assert data.session_category == "race"
    assert data.total_laps == 5


def test_traction_control_and_abs_are_captured_from_car_status(fixture_path) -> None:
    """They exist only in CarStatus; a Session-only read reports 'no assists'."""
    session = sessions_from(fixture_path)[0]
    assert session.traction_control == 2
    assert session.anti_lock_brakes == 1


def test_the_stored_session_is_not_the_menu_uid(ingested) -> None:
    _total, items = catalog.list_sessions(ingested)
    assert len(items) == 1
    assert items[0]["session_uid"] == REFERENCE_UID
    assert items[0]["session_uid"] != "0"


def test_the_assists_summary_names_traction_control(ingested) -> None:
    """A summary built from the Session packet alone would say 'no assists' here."""
    _total, items = catalog.list_sessions(ingested)
    summary = items[0]["assists_summary"]
    assert "TC" in summary
    assert "ABS" in summary
    assert "manual gearbox" in summary
