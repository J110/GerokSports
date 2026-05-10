"""Regression tests for B3-partial: striker cleared on cold-start reject.

Target: score_manager.py:1402-1482 — every False-return path in
`_cold_start_plausible` must clear `self.striker` if it was set, so
stale broadcast reads don't leak striker identity into payloads
emitted while we re-enter cold-start.

Run from repo root:
    pytest files/tests/test_cold_start_striker_clear.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from score_manager import ScoreManager  # noqa: E402


def _sm() -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm._innings_fallback = 1
    sm._last_warm_state = None
    return sm


def test_striker_cleared_on_inn1_impossible_wickets_overs():
    sm = _sm()
    sm.striker = "Rahul Tewatia"
    card = {"score": 5, "wickets": 4, "overs": 0.1}
    assert sm._cold_start_plausible(card) is False
    assert sm.striker is None


def test_striker_cleared_on_inn1_severe_collapse():
    sm = _sm()
    sm.striker = "Some Batter"
    card = {"score": 15, "wickets": 5, "overs": 4.5}
    assert sm._cold_start_plausible(card) is False
    assert sm.striker is None


def test_striker_cleared_on_inn1_score_too_low_for_wickets():
    sm = _sm()
    sm.striker = "Stale Striker"
    card = {"score": 4, "wickets": 3, "overs": 10.0}
    assert sm._cold_start_plausible(card) is False
    assert sm.striker is None


def test_striker_cleared_on_stale_recovery_diff():
    """ref present + diff fails legal cricket transition → striker cleared."""
    sm = _sm()
    sm.striker = "Carry-over Striker"
    sm._last_warm_state = {"score": 50, "wickets": 1, "overs": 7.0}
    # Candidate proposes a backward overs jump → invalid transition
    card = {"score": 60, "wickets": 1, "overs": 5.0}
    assert sm._cold_start_plausible(card) is False
    assert sm.striker is None


def test_striker_cleared_on_validate_absolute_fail():
    """validate_absolute reject (e.g. score > 320) → striker cleared."""
    sm = _sm()
    sm.striker = "Striker"
    card = {"score": 500, "wickets": 0, "overs": 5.0}
    assert sm._cold_start_plausible(card) is False
    assert sm.striker is None


def test_striker_preserved_on_plausible_card():
    sm = _sm()
    sm.striker = "Yashasvi Jaiswal"
    card = {"score": 30, "wickets": 0, "overs": 4.0}
    assert sm._cold_start_plausible(card) is True
    assert sm.striker == "Yashasvi Jaiswal"


def test_no_striker_no_log_emitted(caplog):
    """When striker is already None, the 'also cleared' log line
    must NOT be emitted (avoid log noise)."""
    sm = _sm()
    sm.striker = None
    card = {"score": 5, "wickets": 4, "overs": 0.1}

    import logging
    with caplog.at_level(logging.INFO, logger="SCORE_MGR"):
        assert sm._cold_start_plausible(card) is False

    cleared_logs = [
        rec for rec in caplog.records
        if "also cleared self.striker" in rec.getMessage()
    ]
    assert cleared_logs == [], (
        "expected NO 'also cleared self.striker' log when striker was "
        f"already None, got: {[r.getMessage() for r in cleared_logs]}")
