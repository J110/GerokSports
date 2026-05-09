"""Downstream gate resync on phantom-recovery tests.

P1 fix (2026-05-02 CSK vs MI post-mortem §Issue 3): when a phantom
score / wickets commit gets corrected, ``_last_autodismiss_wickets``
must reset alongside, otherwise the dismiss-replace path stays
stranded for the rest of the innings (CSK vs MI run F167-F699:
195 [DISMISS] Blocked events with last_dismiss_at=3 from the F55
phantom 47/3 commit).

Run from repo root:
    pytest files/tests/test_phantom_recovery_resync.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from eyes.scoreboard import Scoreboard  # noqa: E402


def _make_sb_with_phantom_wickets_3() -> Scoreboard:
    """Build a scoreboard that mimics the F55 phantom 47/3 lock.

    After F55, _inn["wickets"]=3 and _last_autodismiss_wickets is
    seeded to 3 by the cold-start gate (scoreboard.py line 1312).
    """
    sb = Scoreboard()
    sb.batting_team = "Mumbai Indians"
    sb.bowling_team = "Chennai Super Kings"
    sb.current_innings = 1
    sb._inn["score"] = 47
    sb._inn["overs"] = "7.5"
    sb._inn["wickets"] = 3
    sb._last_autodismiss_wickets = 3
    return sb


def test_resync_resets_last_autodismiss_wickets():
    """B1: after phantom recovery, last_autodismiss_wickets must
    track the corrected wicket count, not the phantom value."""
    sb = _make_sb_with_phantom_wickets_3()
    assert sb._last_autodismiss_wickets == 3

    sb.downstream_gates_resync(1, source="test_phantom_recovery")

    assert sb._last_autodismiss_wickets == 1, (
        "_last_autodismiss_wickets must reset to corrected wickets "
        f"value (got {sb._last_autodismiss_wickets})")


def test_resync_idempotent_when_no_regression():
    """If new wickets >= current dismiss gate, resync must not
    advance the gate (gate is one-way upward only via real wickets).
    """
    sb = _make_sb_with_phantom_wickets_3()
    sb.downstream_gates_resync(5, source="test_idempotent")
    assert sb._last_autodismiss_wickets == 3, (
        "resync must only reset gate downward, not upward "
        f"(got {sb._last_autodismiss_wickets})")


def test_resync_drops_tentative_fow_above_new_wickets():
    """Tentative FOW entries above the corrected wickets count are
    dropped and any tentatively-dismissed batter is reactivated."""
    sb = _make_sb_with_phantom_wickets_3()
    sb.fall_of_wickets = [
        Scoreboard.make_fow_placeholder(1),
        Scoreboard.make_fow_placeholder(2),
        Scoreboard.make_fow_placeholder(3),
    ]
    sb.downstream_gates_resync(1, source="test_fow_drop")

    assert len(sb.fall_of_wickets) == 1
    assert sb.fall_of_wickets[0].get("wicket") == 1


def test_resync_preserves_witnessed_fow():
    """Confirmed (non-tentative, non-unwitnessed) FOW entries above
    new wickets must be preserved — they are immutable history."""
    sb = _make_sb_with_phantom_wickets_3()
    sb.fall_of_wickets = [
        {"wicket": 1, "batter": "Will Jacks",
         "score": 1, "overs": "1.1", "_witnessed": True},
        {"wicket": 2, "batter": "Naman Dhir",
         "score": 13, "overs": "5.0", "_witnessed": True},
        Scoreboard.make_fow_placeholder(3),
    ]
    sb.downstream_gates_resync(1, source="test_preserve_witnessed")

    kept_witnessed = [f for f in sb.fall_of_wickets
                      if f.get("_witnessed")]
    assert len(kept_witnessed) == 2, (
        f"Witnessed FOW must survive resync; got {sb.fall_of_wickets}")


def test_dismissal_after_resync_accepted():
    """B6: after resync from phantom 3 → real 1, a subsequent
    dismissal at wickets=2 must be accepted (gate no longer blocks).
    """
    sb = _make_sb_with_phantom_wickets_3()
    sb.downstream_gates_resync(1, source="test_b6")
    assert sb._last_autodismiss_wickets == 1
    sb._inn["wickets"] = 2
    cur_wk = int(sb._inn.get("wickets") or 0)
    last_dismiss = int(sb._last_autodismiss_wickets or 0)
    assert cur_wk > last_dismiss, (
        f"After resync, the dismiss-replace gate (cur_wk > "
        f"last_dismiss) must hold for wkt #2 — got cur_wk={cur_wk}, "
        f"last_dismiss={last_dismiss}")


def test_resync_clears_missing_batter_streak():
    sb = _make_sb_with_phantom_wickets_3()
    sb._missing_batter_streak = {"Naman Dhir": 5}
    sb.downstream_gates_resync(1, source="test_streak_clear")
    assert sb._missing_batter_streak == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
