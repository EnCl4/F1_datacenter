"""T052 -- the lap validity rule, and the single place it lives.

Constitution principle VI. The rule **branches on session type**, and that branch is not
a nicety: the reference race recorded zero invalidated laps across all 22 cars while the
player accumulated two corner-cutting warnings and a penalty. Races penalise; they do not
invalidate. Applying the qualifying rule to a race marks every lap clean, including cut
corners, and manufactures false personal bests.

Computed once here during ingest and stored on the lap, so no client can re-derive it
differently. That is why the API returns every lap with its ``exclusion_reason`` rather
than a pre-filtered list.
"""

from __future__ import annotations

from f1dc.models import (
    EXCLUSION_FIRST_LAP,
    EXCLUSION_IN_LAP,
    EXCLUSION_INCOMPLETE,
    EXCLUSION_INVALIDATED,
    EXCLUSION_OUT_LAP,
    EXCLUSION_PIT,
    EXCLUSION_SAFETY_CAR,
)
from f1dc.wire.f1_2023.enums import PRACTICE, QUALIFYING, RACE, TIME_TRIAL

#: Session categories where the game's own invalidation flag is authoritative.
FLAG_DRIVEN_CATEGORIES = frozenset({PRACTICE, QUALIFYING, TIME_TRIAL})


def evaluate(
    *,
    session_category: str,
    lap_number: int,
    lap_time_ms: int | None,
    valid: bool,
    is_in_lap: bool,
    is_out_lap: bool,
    pit_status: int,
    under_safety_car: bool,
) -> tuple[bool, str | None]:
    """Return ``(counts, exclusion_reason)`` for one lap.

    ``counts`` means "include this lap in pace statistics and personal bests". A lap that
    does not count is still recorded and returned -- it is excluded, not hidden.
    """
    if lap_time_ms is None or lap_time_ms <= 0:
        return False, EXCLUSION_INCOMPLETE

    # Pit involvement is never representative pace, in any session type.
    #
    # Order matters. pit_status is the strongest evidence -- it says the car was in the
    # pit lane -- so it is checked first. The reference race's pit lap reports BOTH
    # in-lap and out-lap driver status within the same lap, and calling that lap an
    # "out lap" would describe it wrongly; it is the pit lap.
    if pit_status != 0:
        return False, EXCLUSION_PIT
    if is_in_lap:
        return False, EXCLUSION_IN_LAP
    if is_out_lap:
        return False, EXCLUSION_OUT_LAP

    if session_category in FLAG_DRIVEN_CATEGORIES:
        # Practice, qualifying, time trial: the game invalidates laps directly.
        if not valid:
            return False, EXCLUSION_INVALIDATED
        return True, None

    if session_category == RACE:
        # Races do not invalidate; they warn and penalise. So validity is inferred from
        # circumstance instead.
        if under_safety_car:
            return False, EXCLUSION_SAFETY_CAR
        if lap_number <= 1:
            # A standing start makes lap 1 incomparable with any other lap.
            return False, EXCLUSION_FIRST_LAP
        return True, None

    # Unknown category: be conservative rather than inventing a personal best.
    if not valid:
        return False, EXCLUSION_INVALIDATED
    return True, None


def best_lap(laps: list) -> tuple[int | None, int | None]:
    """Fastest **counting** lap as ``(time_ms, lap_number)``.

    FR-024: a lap that did not count, or came from an abandoned session, must never be
    presented as a personal best.
    """
    candidates = [
        lap for lap in laps if lap.counts and lap.lap_time_ms and lap.lap_time_ms > 0
    ]
    if not candidates:
        return None, None
    best = min(candidates, key=lambda lap: lap.lap_time_ms)
    return best.lap_time_ms, best.lap_number
