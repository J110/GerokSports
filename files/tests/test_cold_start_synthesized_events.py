"""Tests for cold-start ball-event synthesis at WARM transition.

Target: score_manager.py — `_synthesize_cold_start_ball_events` and the
`_maybe_synthesize_cold_start_gap` call wired into every COLD_START →
WARM transition site.

Run from repo root:
    pytest files/tests/test_cold_start_synthesized_events.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from score_manager import ScoreManager  # noqa: E402


def _sm() -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm._innings_fallback = 1
    sm._last_warm_state = None
    return sm


# -- _synthesize_cold_start_ball_events distribution heuristics ----------

def test_synth_boundary_runs_4_attributes_to_last_ball():
    sm = _sm()
    events = sm._synthesize_cold_start_ball_events(
        implied_balls=2, implied_runs=4, implied_wickets=0)
    tokens = [e["token"] for e in events]
    assert tokens == [".", "4"]


def test_synth_boundary_runs_6_attributes_to_last_ball():
    sm = _sm()
    events = sm._synthesize_cold_start_ball_events(
        implied_balls=3, implied_runs=6, implied_wickets=0)
    tokens = [e["token"] for e in events]
    assert tokens == [".", ".", "6"]


def test_synth_zero_runs_all_dots():
    sm = _sm()
    events = sm._synthesize_cold_start_ball_events(
        implied_balls=3, implied_runs=0, implied_wickets=0)
    assert [e["token"] for e in events] == [".", ".", "."]


def test_synth_singles_then_dots_when_runs_lte_balls():
    sm = _sm()
    events = sm._synthesize_cold_start_ball_events(
        implied_balls=4, implied_runs=2, implied_wickets=0)
    # spec: dots first, then ones
    assert [e["token"] for e in events] == [".", ".", "1", "1"]


def test_synth_runs_exceed_balls_excess_to_last():
    """5 runs in 2 balls (not 4/6): heuristic ones + last-ball excess."""
    sm = _sm()
    events = sm._synthesize_cold_start_ball_events(
        implied_balls=2, implied_runs=5, implied_wickets=0)
    assert [e["token"] for e in events] == ["1", "4"]


def test_synth_zero_balls_returns_empty():
    sm = _sm()
    events = sm._synthesize_cold_start_ball_events(
        implied_balls=0, implied_runs=0, implied_wickets=0)
    assert events == []


def test_synth_populates_this_over_with_tokens():
    sm = _sm()
    sm._synthesize_cold_start_ball_events(
        implied_balls=2, implied_runs=4, implied_wickets=0)
    assert sm.this_over == [".", "4"]
    # this_over_src marker so post-mortem audit can identify synthesised
    # tokens (vs observed via "obs" / "bcast" / placeholder "?").
    assert sm.this_over_src == ["synth", "synth"]


def test_synth_records_runs_correctly_in_events():
    sm = _sm()
    events = sm._synthesize_cold_start_ball_events(
        implied_balls=2, implied_runs=4, implied_wickets=0)
    assert events[0]["runs"] == 0
    assert events[1]["runs"] == 4
    assert events[0]["synthesized"] is True
    assert events[1]["synthesized"] is True


def test_synth_persists_to_attribute_for_drain():
    sm = _sm()
    sm._synthesize_cold_start_ball_events(
        implied_balls=3, implied_runs=6, implied_wickets=0)
    # exposed for downstream pickup (over_mgr, trace replay)
    assert len(sm._cold_start_synthesized_events) == 3
    assert sm._cold_start_synthesized_events[-1]["token"] == "6"


# -- _maybe_synthesize_cold_start_gap delta computation ------------------

def test_maybe_synth_no_op_at_zero_gap():
    sm = _sm()
    # Anchor matches entry — no balls passed
    sm.score = 0
    sm.wickets = 0
    sm.overs = 0.0
    sm._maybe_synthesize_cold_start_gap()
    assert sm._cold_start_synthesized_events == []


def test_maybe_synth_computes_gap_4_runs_2_balls():
    sm = _sm()
    sm.score = 4
    sm.wickets = 0
    sm.overs = 0.2
    sm._maybe_synthesize_cold_start_gap()
    assert sm._cold_start_synthesized_events != []
    assert [e["token"] for e in sm._cold_start_synthesized_events] == [".", "4"]


def test_maybe_synth_first_over_completed():
    """0/0/0.0 → 7/0/1.0: 6 balls, 7 runs. Heuristic spreads dots+singles
    then attributes excess to last."""
    sm = _sm()
    sm.score = 7
    sm.wickets = 0
    sm.overs = 1.0
    sm._maybe_synthesize_cold_start_gap()
    tokens = [e["token"] for e in sm._cold_start_synthesized_events]
    assert len(tokens) == 6  # 6 legal balls in a completed over
    assert sum(0 if t == "." else int(t) for t in tokens) == 7


def test_maybe_synth_records_implied_wickets_in_trace_only():
    """Wickets are not distributed across balls but should be captured in
    the synthesised gap metadata so post-match audit can flag them.
    """
    sm = _sm()
    sm.score = 4
    sm.wickets = 1
    sm.overs = 0.2
    sm._maybe_synthesize_cold_start_gap()
    # Token distribution unchanged by wicket count
    assert [e["token"] for e in sm._cold_start_synthesized_events] == [".", "4"]
