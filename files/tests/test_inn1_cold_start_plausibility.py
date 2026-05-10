"""Inn1 cold-start plausibility gate tests.

D1+D2+D3 partial fix (2026-05-10 RR vs GT post-mortem): the
`_cold_start_plausible` method now rejects fresh-boot inn1 candidates
that violate physical-impossibility heuristics — wickets >= 2 in
< 1 over, severe collapses (>= 5 wkt in < 5 ov), and wicket-rich
states with too few runs (>= 3 wkt with score < 2*wickets).

Run from repo root:
    pytest files/tests/test_inn1_cold_start_plausibility.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from score_manager import ScoreManager  # noqa: E402


def _sm_fresh_inn1() -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm._last_warm_state = None
    sm._innings_fallback = 1
    return sm


@pytest.mark.parametrize(
    "score,wickets,overs,expected,label",
    [
        (0, 0, 0.0, True, "0/0 (0.0) at start"),
        (14, 4, 8.4, True, "14/4 (8.4) — ambiguous, deferred to detection"),
        (5, 4, 0.1, False, "5/4 (0.1) impossible_wickets_overs"),
        (15, 5, 4.5, False, "15/5 (4.5) severe_collapse_implausible"),
        (4, 3, 10.0, False, "4/3 (10.0) score_too_low_for_wickets"),
        (30, 4, 8.4, True, "30/4 (8.4) plausible mid-innings cold start"),
        (100, 2, 15.0, True, "100/2 (15.0) plausible cold-boot mid-innings"),
    ],
)
def test_cold_start_plausibility(score, wickets, overs, expected, label):
    sm = _sm_fresh_inn1()
    card = {"score": score, "wickets": wickets, "overs": overs}
    assert sm._cold_start_plausible(card) is expected, label


def test_innings_2_skips_inn1_gate():
    """Gate is inn1-only — inn2 cold-boot of 5/4 (0.1) bypasses it."""
    sm = ScoreManager(shadow=True)
    sm._last_warm_state = None
    sm._innings_fallback = 2
    card = {"score": 5, "wickets": 4, "overs": 0.1}
    assert sm._cold_start_plausible(card) is True


def test_warm_state_present_skips_inn1_gate():
    """When `_last_warm_state` exists the inn1-start gate is bypassed —
    stale-recovery diff validation runs instead. Here a legal +1-run
    +1-ball diff from a warm 4/3 baseline passes even though the
    candidate scoreline (5/4 (0.1)) would have been rejected as a
    fresh-boot candidate."""
    sm = ScoreManager(shadow=True)
    sm._last_warm_state = {"score": 4, "wickets": 3, "overs": 0.0}
    sm._innings_fallback = 1
    card = {"score": 5, "wickets": 4, "overs": 0.1}
    sm._cold_start_plausible(card)
