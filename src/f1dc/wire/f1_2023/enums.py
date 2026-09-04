"""T014 -- F1 23 enumerations and their human-readable names.

``SESSION_CATEGORY`` is the important one: it is what makes the lap-validity rule branch
(constitution principle VI, FR-012). Races penalise rather than invalidate, so applying
the qualifying rule to a race marks every lap clean, including cut corners.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------------------
# Circuits
# --------------------------------------------------------------------------------------

TRACKS: Final[dict[int, str]] = {
    0: "Melbourne",
    1: "Paul Ricard",
    2: "Shanghai",
    3: "Bahrain",
    4: "Catalunya",
    5: "Monaco",
    6: "Montreal",
    7: "Silverstone",
    8: "Hockenheim",
    9: "Hungaroring",
    10: "Spa",
    11: "Monza",
    12: "Singapore",
    13: "Suzuka",
    14: "Abu Dhabi",
    15: "Texas",
    16: "Interlagos",
    17: "Austria",
    18: "Sochi",
    19: "Mexico",
    20: "Baku",
    21: "Bahrain Short",
    22: "Silverstone Short",
    23: "Texas Short",
    24: "Suzuka Short",
    25: "Hanoi",
    26: "Zandvoort",
    27: "Imola",
    28: "Portimao",
    29: "Jeddah",
    30: "Miami",
    31: "Las Vegas",
    32: "Losail",
}

#: Shortened layouts share a circuit with their full-length sibling but not its geometry,
#: so (track_id, lap_distance) is only a safe comparison key within the same id. The
#: project owner drives official full-length circuits only, but this is recorded so a
#: future feature does not assume it.
SHORT_LAYOUTS: Final[frozenset[int]] = frozenset({21, 22, 23, 24})

# --------------------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------------------

SESSION_TYPES: Final[dict[int, str]] = {
    0: "Unknown",
    1: "P1",
    2: "P2",
    3: "P3",
    4: "Short P",
    5: "Q1",
    6: "Q2",
    7: "Q3",
    8: "Short Q",
    9: "OSQ",
    10: "Race",
    11: "Race 2",
    12: "Race 3",
    13: "Time Trial",
}

PRACTICE = "practice"
QUALIFYING = "qualifying"
RACE = "race"
TIME_TRIAL = "time_trial"
UNKNOWN_CATEGORY = "unknown"

#: Maps the game's session type to the category that governs lap validity.
SESSION_CATEGORY: Final[dict[int, str]] = {
    0: UNKNOWN_CATEGORY,
    1: PRACTICE,
    2: PRACTICE,
    3: PRACTICE,
    4: PRACTICE,
    5: QUALIFYING,
    6: QUALIFYING,
    7: QUALIFYING,
    8: QUALIFYING,
    9: QUALIFYING,
    10: RACE,
    11: RACE,
    12: RACE,
    13: TIME_TRIAL,
}

WEATHER: Final[dict[int, str]] = {
    0: "clear",
    1: "light cloud",
    2: "overcast",
    3: "light rain",
    4: "heavy rain",
    5: "storm",
}

SAFETY_CAR_STATUS: Final[dict[int, str]] = {
    0: "none",
    1: "full",
    2: "virtual",
    3: "formation lap",
}

# --------------------------------------------------------------------------------------
# Tyres
# --------------------------------------------------------------------------------------

ACTUAL_TYRE_COMPOUNDS: Final[dict[int, str]] = {
    7: "Intermediate",
    8: "Wet",
    9: "Wet (F2 classic)",
    11: "Super Soft (F2)",
    12: "Soft (F2)",
    13: "Medium (F2)",
    14: "Hard (F2)",
    15: "Wet (F2)",
    16: "C5",
    17: "C4",
    18: "C3",
    19: "C2",
    20: "C1",
    21: "C0",
}

VISUAL_TYRE_COMPOUNDS: Final[dict[int, str]] = {
    7: "Intermediate",
    8: "Wet",
    16: "Soft",
    17: "Medium",
    18: "Hard",
    19: "Super Soft (F2)",
    20: "Soft (F2)",
    21: "Medium (F2)",
    22: "Hard (F2)",
}

# --------------------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------------------

DRIVER_STATUS: Final[dict[int, str]] = {
    0: "in garage",
    1: "flying lap",
    2: "in lap",
    3: "out lap",
    4: "on track",
}

RESULT_STATUS: Final[dict[int, str]] = {
    0: "invalid",
    1: "inactive",
    2: "active",
    3: "finished",
    4: "did not finish",
    5: "disqualified",
    6: "not classified",
    7: "retired",
}

PIT_STATUS: Final[dict[int, str]] = {0: "none", 1: "pitting", 2: "in pit area"}

# --------------------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------------------

#: Four-character event codes. Every one of these except the commented group was observed
#: in the reference capture.
EVENT_CODES: Final[dict[str, str]] = {
    "SSTA": "session started",
    "SEND": "session ended",
    "FTLP": "fastest lap",
    "RTMT": "retirement",
    "DRSE": "DRS enabled",
    "DRSD": "DRS disabled",
    "TMPT": "team mate in pits",
    "CHQF": "chequered flag",
    "RCWN": "race winner",
    "PENA": "penalty issued",
    "SPTP": "speed trap triggered",
    "STLG": "start lights",
    "LGOT": "lights out",
    "DTSV": "drive-through served",
    "SGSV": "stop-go served",
    "FLBK": "flashback",
    "BUTN": "button status",
    "RDFL": "red flag",
    "OVTK": "overtake",
}

#: Events that mean the session reached its natural end (FR-014, R7).
SESSION_END_EVENTS: Final[frozenset[str]] = frozenset({"SEND", "CHQF"})


# --------------------------------------------------------------------------------------
# Lookup helpers -- unknown ids are labelled, never silently dropped
# --------------------------------------------------------------------------------------


def _lookup(table: dict[int, str], value: int, kind: str) -> str:
    return table.get(value, f"unknown {kind} {value}")


def track_name(track_id: int) -> str:
    return _lookup(TRACKS, track_id, "track")


def session_type_name(session_type: int) -> str:
    return _lookup(SESSION_TYPES, session_type, "session type")


def session_category(session_type: int) -> str:
    return SESSION_CATEGORY.get(session_type, UNKNOWN_CATEGORY)


def weather_name(weather: int) -> str:
    return _lookup(WEATHER, weather, "weather")


def actual_compound_name(compound: int) -> str:
    return _lookup(ACTUAL_TYRE_COMPOUNDS, compound, "compound")


def visual_compound_name(compound: int) -> str:
    return _lookup(VISUAL_TYRE_COMPOUNDS, compound, "compound")


def driver_status_name(status: int) -> str:
    return _lookup(DRIVER_STATUS, status, "driver status")


def result_status_name(status: int) -> str:
    return _lookup(RESULT_STATUS, status, "result status")


def event_description(code: str) -> str:
    return EVENT_CODES.get(code, f"unknown event {code}")
