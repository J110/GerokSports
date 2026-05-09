"""Wire — single-line factual commentary for each delivery.

A format string, not an LLM call.  Every word comes from data.
Zero latency, zero hallucination.

Format:
    {over}.{ball}: {bowler} to {striker} — {outcome}{, enrichment}{(speed)}. {score}/{wickets}
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from score_manager import ScoreManager


def _format_overs(overs: object) -> str:
    """Return cricket overs as X.Y without treating it as base-10 math."""
    if overs is None or overs == "":
        return "0.0"
    s = str(overs).strip()
    if "." in s:
        whole_s, ball_s = s.split(".", 1)
        try:
            whole = int(whole_s or 0)
            ball = int((ball_s or "0")[:1])
        except (TypeError, ValueError):
            return "0.0"
        return f"{whole}.{ball}"
    try:
        return f"{int(float(s))}.0"
    except (TypeError, ValueError):
        return "0.0"


def format_absorbed_gap_wire(gap_parent: dict, snap: dict,
                             state: "ScoreManager") -> str:
    """Single-line factual summary for a decomposed absorbed gap (D1).

    Uses aggregate gap_parent metadata — no per-ball narrative.
    """
    ob = _format_overs(snap.get("overs"))
    bowler_info = snap.get("bowler") or {}
    bowler = bowler_info.get("name") or "bowler"
    striker = snap.get("striker") or "batter"
    n = gap_parent.get("balls_skipped")
    if n is None:
        n = gap_parent.get("balls_missed") or 0
    r = gap_parent.get("runs")
    if r is None:
        r = gap_parent.get("total_runs")
    wq = gap_parent.get("wickets_in_gap")
    if n is None:
        n = 0
    wpart = (
        f", wickets in gap: {wq}" if wq is not None else "")
    outcome = (
        f"absorbed {int(n)} legal balls (team runs in gap: {r}"
        f"{wpart}; per-ball detail withheld — Policy U)")
    line = f"{ob}: {bowler} to {striker} — {outcome}"
    speed = snap.get("speed_kph") or (state.last_speed if state else None)
    if speed:
        line += f" ({speed} kph)"
    score = snap.get("score")
    wickets = snap.get("wickets")
    if score is not None and wickets is not None:
        line += f". {score}/{wickets}"
    return line


def format_wire(event: dict, snap: dict, state: "ScoreManager") -> str | None:
    """Build a single Wire commentary line.

    Returns ``None`` for per-ball :data:`~score_manager.ABSORBED_LEGAL`
    events — callers emit one :func:`format_absorbed_gap_wire` summary.
    """
    etype = event.get("type", "")
    if etype == "ABSORBED_LEGAL":
        return None

    ob = _format_overs(snap.get("overs"))

    bowler_info = snap.get("bowler") or {}
    bowler = bowler_info.get("name") or "bowler"
    striker = event.get("striker") or "batter"

    runs = event.get("runs", 0)

    if etype == "DOT":
        outcome = "no run"
    elif etype == "RUNS":
        outcome = f"{runs} run{'s' if runs != 1 else ''}"
    elif etype == "FOUR":
        outcome = "FOUR"
    elif etype == "SIX":
        outcome = "SIX"
    elif etype == "WICKET":
        dismissed = event.get("dismissed")
        if dismissed:
            outcome = f"{dismissed} is OUT"
        else:
            outcome = "OUT"
        wt = event.get("wicket_type")
        if wt and wt != "unknown":
            outcome += f" ({wt.replace('_', ' ')})"
        if runs and runs > 0:
            outcome += f", {runs} run{'s' if runs != 1 else ''}"
    elif etype == "WIDE":
        outcome = "wide"
    elif etype == "NO_BALL":
        batter_runs = event.get("batter_runs")
        if batter_runs and batter_runs > 0:
            outcome = (f"no ball, {batter_runs} "
                       f"run{'s' if batter_runs != 1 else ''}")
        else:
            outcome = "no ball"
    elif etype == "LEG_BYE":
        outcome = f"leg bye, {runs} run{'s' if runs != 1 else ''}"
    elif etype == "MULTI_BALL":
        overs_skipped = event.get("overs_skipped", 0)
        balls_count = round(overs_skipped * 10)
        outcome = f"{runs} runs off {balls_count} balls"
    elif etype == "EXTRA":
        outcome = f"{runs} extra{'s' if runs != 1 else ''}"
    else:
        outcome = f"{runs} run{'s' if runs != 1 else ''}"

    line = f"{ob}: {bowler} to {striker} — {outcome}"

    delivery = event.get("delivery")
    if delivery:
        parts: list[str] = []
        length = delivery.get("length")
        if length and length != "unknown":
            parts.append(length.replace("_", " "))
        direction = delivery.get("direction")
        if direction and direction != "unknown":
            parts.append(f"through the {direction.replace('_', ' ')}")
        elevation = delivery.get("elevation")
        if elevation == "in_the_air":
            parts.append("in the air")
        if parts:
            line += f", {', '.join(parts)}"

    speed = snap.get("speed_kph") or (state.last_speed if state else None)
    if speed:
        line += f" ({speed} kph)"

    score = snap.get("score")
    wickets = snap.get("wickets")
    if score is not None and wickets is not None:
        line += f". {score}/{wickets}"

    if event.get("is_free_hit"):
        line = "FREE HIT — " + line

    return line
