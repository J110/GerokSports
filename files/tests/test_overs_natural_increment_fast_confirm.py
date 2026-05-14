"""Tests for the match-level overs natural-increment fast-confirm path
in `consistent_tracker.ConsistentReadTracker`.

Investigation 2 (2026-05-14): the pending-defer at consistent_tracker:462-465
required 2 reads of any warm-state value change before committing, which
swallowed legitimate over-rollover reads (X.5 → (X+1).0) on first sight.
With score post-event-grace bypass landing the same frame's score
update, the downstream extras-inference at score_manager:2965 saw
d_score>0 + d_overs=0 and fabricated a phantom Wd.

Run from repo root:
    pytest files/tests/test_overs_natural_increment_fast_confirm.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.consistent_tracker import ConsistentReadTracker  # noqa: E402


def _t() -> ConsistentReadTracker:
    return ConsistentReadTracker()


# -- helper invariants ----------------------------------------------------

def test_within_over_increment_detected():
    assert ConsistentReadTracker._is_natural_overs_increment("overs", "0.3", "0.4")
    assert ConsistentReadTracker._is_natural_overs_increment("overs", "5.0", "5.1")
    assert ConsistentReadTracker._is_natural_overs_increment("overs", "12.4", "12.5")


def test_over_rollover_detected():
    assert ConsistentReadTracker._is_natural_overs_increment("overs", "0.5", "1.0")
    assert ConsistentReadTracker._is_natural_overs_increment("overs", "5.5", "6.0")
    assert ConsistentReadTracker._is_natural_overs_increment("overs", "19.5", "20.0")


def test_multi_ball_jump_not_natural():
    # Two-ball gap is legal (via _decompose_multi_ball) but not the
    # "natural" single-ball fast-path.
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "overs", "0.3", "0.5")
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "overs", "0.5", "1.1")
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "overs", "0.0", "0.2")


def test_backwards_not_natural():
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "overs", "1.0", "0.5")
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "overs", "5.3", "5.2")


def test_non_overs_field_rejected():
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "score", "5", "6")
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "bowl:foo:overs", "0.5", "1.0")  # bowler overs go through
                                          # _is_natural_bowler_increment


def test_unparseable_value_rejected():
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "overs", "null", "1.0")
    assert not ConsistentReadTracker._is_natural_overs_increment(
        "overs", "0.5", "foo")


# -- end-to-end: tracker.update commits on first sight -------------------

def test_update_commits_within_over_on_first_sight():
    """Investigation 2 regression: 0.3 → 0.4 single-ball delta must
    commit immediately without going through the 2-frame pending defer."""
    t = _t()
    t.confirmed["overs"] = "0.3"
    out = t.update("overs", "0.4", frame_count=10)
    assert out == "0.4"
    assert t.confirmed["overs"] == "0.4"
    # pending must be clean — no defer
    assert "overs" not in t.pending


def test_update_commits_over_rollover_on_first_sight():
    """The bug from investigation 2 — F53 read 0.5→1.0 was dropped onto
    the floor, leading to a fabricated Wd downstream."""
    t = _t()
    t.confirmed["overs"] = "0.5"
    out = t.update("overs", "1.0", frame_count=53)
    assert out == "1.0"
    assert t.confirmed["overs"] == "1.0"
    assert "overs" not in t.pending


def test_update_two_ball_jump_falls_to_pending():
    """A two-ball delta is not natural — must defer for cross-check."""
    t = _t()
    t.confirmed["overs"] = "0.3"
    out = t.update("overs", "0.5", frame_count=10)
    # Falls into pending (returns current), confirmed unchanged
    assert out == "0.3"
    assert t.confirmed["overs"] == "0.3"
    assert "overs" in t.pending


def test_update_backwards_falls_to_suspicious():
    """Backwards is suspicious — must not commit via fast-path."""
    t = _t()
    t.confirmed["overs"] = "1.0"
    out = t.update("overs", "0.5", frame_count=10)
    # Suspicious path returns current
    assert out == "1.0"
    assert t.confirmed["overs"] == "1.0"
