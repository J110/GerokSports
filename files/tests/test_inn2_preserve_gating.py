"""D4 inn2 preserve gating tests.

The inn1→inn2 preserve heuristic in `test_pipeline._set_innings_2_logged`
adds a third condition on top of (has_progress AND impossible_end):
the score must have actually advanced WHILE in WARM mode. Without this,
a cold-start commit that immediately freezes on a stale broadcast
graphic (e.g. RR vs GT 2026-05-08, F920 commits 14/4 (8.4) and never
moves) gets carried into inn2 as a "preserve".

These tests exercise the SM-side flag (`_warm_advancing_observed`)
since the pipeline gate just reads it via `getattr`.

Run from repo root:
    pytest files/tests/test_inn2_preserve_gating.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from score_manager import ScoreManager  # noqa: E402


def _sm_warm(score: int, wickets: int, overs: float) -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm.mode = "WARM"
    sm._sm_scalar_fallback["score"] = score
    sm._sm_scalar_fallback["wickets"] = wickets
    sm.overs = overs
    sm._innings_fallback = 1
    return sm


def _gate_decision(sm: ScoreManager, pre_score: int,
                   pre_wkts: int, pre_overs: float) -> str:
    """Replicate the pipeline gate at test_pipeline.py:5676-5697."""
    has_progress = (pre_score > 0 or pre_overs > 0.0)
    impossible_end = (pre_overs < 18.0 and pre_wkts < 8)
    warm_advanced = bool(getattr(sm, "_warm_advancing_observed", False))
    if has_progress and impossible_end and warm_advanced:
        return "preserve"
    if has_progress and impossible_end:
        return "drop"
    return "noop"


def test_initial_flag_is_false():
    sm = ScoreManager(shadow=True)
    assert sm._warm_advancing_observed is False


def test_warm_advance_sets_flag():
    sm = _sm_warm(score=14, wickets=0, overs=2.0)
    sm._accept_update({"score": 18}, frame=10)
    assert sm._warm_advancing_observed is True


def test_cold_start_commit_does_not_set_flag():
    sm = ScoreManager(shadow=True)
    sm.mode = "COLD_START"
    sm._sm_scalar_fallback["score"] = None
    sm._accept_update({"score": 14}, frame=920)
    assert sm._warm_advancing_observed is False


def test_warm_no_advance_does_not_set_flag():
    sm = _sm_warm(score=14, wickets=4, overs=8.4)
    sm._accept_update({"score": 14}, frame=921)
    assert sm._warm_advancing_observed is False


def test_stuck_cold_start_drops_state():
    """RR vs GT 2026-05-08 reproduction: inn1 committed 14/4 (8.4)
    via cold-start at F920, no live update ever advanced the score
    (every subsequent frame rejected as overs regression). At inn2
    flip, the gate must NOT preserve — score never advanced WARM."""
    sm = ScoreManager(shadow=True)
    sm.mode = "COLD_START"
    sm._accept_update({"score": 14, "wickets": 4, "overs": 8.4}, frame=920)
    assert sm._warm_advancing_observed is False
    assert _gate_decision(sm, 14, 4, 8.4) == "drop"


def test_real_mid_inn2_restart_preserves():
    """Pipeline boots mid-inn2 at 35/0 (5.2). Live broadcast advances
    score over the next 30 frames to 50/1 (8.0). At the next
    `set_innings_2` flip, the gate MUST preserve the inn2 progress."""
    sm = _sm_warm(score=35, wickets=0, overs=5.2)
    for nxt in (38, 42, 47, 50):
        sm._accept_update({"score": nxt}, frame=100)
    assert sm._warm_advancing_observed is True
    assert _gate_decision(sm, 50, 1, 8.0) == "preserve"


def test_zero_progress_is_noop():
    sm = ScoreManager(shadow=True)
    assert _gate_decision(sm, 0, 0, 0.0) == "noop"
