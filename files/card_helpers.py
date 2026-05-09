"""Shared helpers for bowler overs reconciliation and card shaping.

Imported by ``score_manager`` and ``test_pipeline``.  Must not import either
of those modules — avoids cycles.  Intentionally excludes vision/YOLO and
other heavy pipeline dependencies.
"""
from __future__ import annotations

from eyes.commentary import overs_to_balls
from eyes.cricket_logger import CricketLogger

log = CricketLogger("CARD_HELPERS")


def _balls_to_overs_str(balls: int) -> str:
    """Inverse of overs_to_balls. 6 -> '1.0', 11 -> '1.5', 13 -> '2.1'.

    Display-convention note: the 6th legal ball of an over is rendered
    as the *next* over's `.0` position because of integer-divide
    arithmetic — 71 balls -> '11.5' (5 legal balls into over 12) and
    72 balls -> '12.0' (12 complete overs, 0 balls into over 13).
    There is no '11.6' representation in this scheme; CB displays the
    same ball as '11.6' (1-6 within-over), while the pipeline collapses
    it into '12.0' (0-5 within-over plus a "completed" marker).  When
    reconciling with CB ball-by-ball, treat pipeline `(N+1).0` as
    equivalent to CB `(N).6`: a sequence like
    `47/4 (11.5) → 51/4 (12.0)` represents the boundary on the 6th
    ball of over 12 finishing the over with score 51/4.  Score and
    over-count are correct; only the ball-position label differs.
    """
    return f"{balls // 6}.{balls % 6}"


def _reconcile_bowler_overs(
        bowling_card: list[dict],
        team_overs: str | float | None,
        current_bowler: str | None) -> list[dict]:
    """Cross-field consistency for bowler overs vs. team overs.

    Cricket invariant: a bowler bowls a complete over (no mid-over
    bowler changes in T20). When team overs cross a whole boundary
    (X.0), the bowler who bowled that closing ball MUST have their
    overs ending in .0 too. Anything else is logically impossible.

    The Scout/Extractor pipeline can briefly miss the closing ball of
    an over for the bowler (broadcast strip flickers, scout reads a
    stale frame, etc.) — leaving e.g. team=1.0 / bowler=0.5 in the UI.
    This helper snaps the **current bowler's** overs forward to the
    next whole boundary when (and only when) the team has clearly
    crossed one and the bowler is lagging by ≤5 balls within the same
    incomplete over.

    We never push a bowler's overs PAST team overs, and we never
    snap a non-current bowler (their spell already ended; their card
    figure is final).
    """
    if not bowling_card or not current_bowler or team_overs is None:
        return bowling_card
    try:
        team_balls = overs_to_balls(str(team_overs))
    except (ValueError, TypeError, AttributeError):
        return bowling_card
    if team_balls <= 0 or team_balls % 6 != 0:
        return bowling_card

    for entry in bowling_card:
        if entry.get("name") != current_bowler:
            continue
        try:
            bow_balls = overs_to_balls(str(entry.get("overs") or "0"))
        except (ValueError, TypeError, AttributeError):
            return bowling_card
        if bow_balls % 6 == 0:
            return bowling_card
        snapped_balls = ((bow_balls // 6) + 1) * 6
        if snapped_balls > team_balls:
            return bowling_card
        snapped_overs = _balls_to_overs_str(snapped_balls)
        log.info(
            f"  [CONSISTENCY] {current_bowler} overs "
            f"{entry.get('overs')} → {snapped_overs} "
            f"(team @ {team_overs}, bowler must finish over)")
        entry["overs"] = snapped_overs
        if entry.get("runs") is not None and snapped_balls > 0:
            entry["economy"] = round(
                entry["runs"] / (snapped_balls / 6), 1)
        return bowling_card
    return bowling_card


__all__ = [
    "overs_to_balls",
    "_balls_to_overs_str",
    "_reconcile_bowler_overs",
]
