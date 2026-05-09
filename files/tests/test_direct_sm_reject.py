"""DIRECT path cricket-rules pre-check tests.

P0 fix (2026-05-02 CSK vs MI post-mortem §Issue 2): the DIRECT
extractor → tracker block in `test_pipeline.py` now runs the
cricket_rules validator BEFORE mutating ``scoreboard._inn``.
Without this gate, a recap-overlay frame at F500 19:57:07 was able
to commit overs 5.2→7.5 (Δ_balts=15, well beyond MULTI_BALL_MAX_BALLS
=12); the SM REJECT log fired one frame later and could no longer
revert the commit.

Run from repo root:
    pytest files/tests/test_direct_sm_reject.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from cricket_rules import validate_direct_proposal  # noqa: E402
from eyes.scoreboard import Scoreboard  # noqa: E402


def test_overs_jump_5_2_to_7_5_rejected():
    """F500 reproduction: real broadcast at MI 53/1 (5.2), recap
    overlay proposes 49-3 (7.5). overs Δ_balts=15 > 12 — must reject.
    """
    res = validate_direct_proposal(
        cur_score=53, cur_overs="5.2", cur_wickets=1,
        new_score=49, new_overs="7.5", new_wickets=3,
        target=None, innings=1)
    assert not res.ok
    assert res.reject_reason is not None
    assert "d_balts" in res.reject_reason or "negative" in res.reject_reason


def test_overs_jump_overs_only_field_rejected():
    """Reduced case where extractor omits score/wickets but proposes
    a 5.2→7.5 overs jump alone. Must still reject — d_balts=15 > 12.
    """
    res = validate_direct_proposal(
        cur_score=53, cur_overs="5.2", cur_wickets=1,
        new_score=None, new_overs="7.5", new_wickets=None,
        target=None, innings=1)
    assert not res.ok
    assert "d_balts" in res.reject_reason


def test_normal_overs_increment_accepted():
    """5.2 → 5.3 is the canonical ball-by-ball tick — must accept."""
    res = validate_direct_proposal(
        cur_score=53, cur_overs="5.2", cur_wickets=1,
        new_score=53, new_overs="5.3", new_wickets=1,
        target=None, innings=1)
    assert res.ok


def test_cold_start_passes():
    """Pre-check must not block the very first commit (current state
    is still None). validate_diff requires a baseline."""
    res = validate_direct_proposal(
        cur_score=None, cur_overs=None, cur_wickets=None,
        new_score=47, new_overs="7.5", new_wickets=3,
        target=None, innings=1)
    assert res.ok


def test_direct_path_state_unchanged_on_reject():
    """End-to-end: simulate the DIRECT path's gate behavior.
    Scoreboard at 53/1 (5.2). cricket_rules rejects 7.5 jump.
    Therefore scoreboard.set should not be called; state stays.
    """
    sb = Scoreboard()
    sb.batting_team = "Mumbai Indians"
    sb.bowling_team = "Chennai Super Kings"
    sb.current_innings = 1
    sb._inn["score"] = 53
    sb._inn["overs"] = "5.2"
    sb._inn["wickets"] = 1
    sb._tracker.confirmed["score"] = 53
    sb._tracker.confirmed["overs"] = "5.2"
    sb._tracker.confirmed["wickets"] = 1

    res = validate_direct_proposal(
        cur_score=sb._inn["score"],
        cur_overs=sb._inn["overs"],
        cur_wickets=sb._inn["wickets"],
        new_score=49, new_overs="7.5", new_wickets=3,
        target=None, innings=1)

    if res.ok:
        sb.set("overs", "7.5", frame=500)

    assert sb._inn["overs"] == "5.2", (
        "DIRECT pre-check must abort overs commit when cricket_rules "
        f"rejects (got {sb._inn['overs']}, reject_reason="
        f"{res.reject_reason})")


def test_score_regression_rejected():
    """Recap overlay with score lower than live state → d_score<0
    must reject regardless of overs."""
    res = validate_direct_proposal(
        cur_score=53, cur_overs="5.2", cur_wickets=1,
        new_score=49, new_overs="5.3", new_wickets=1,
        target=None, innings=1)
    assert not res.ok
    assert "d_score" in res.reject_reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
