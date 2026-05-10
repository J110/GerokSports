"""Regression tests for B1: cold-start max-frames gate.

Target: score_manager.py:1278-1285 — when cold_frames reaches the
give-up boundary, an implausible candidate must NOT be committed.
Instead the deferral path resets cold_frames=0 and stays COLD_START.

Run from repo root:
    pytest files/tests/test_cold_start_max_frames_gate.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from score_manager import (  # noqa: E402
    COLD_MAX_FRAMES, FrameInput, ScoreManager,
)


def _sm() -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm._innings_fallback = 1
    sm._last_warm_state = None
    return sm


def _frame() -> FrameInput:
    return FrameInput(frame_id="f", timestamp=0.0)


def test_f1126_replica_3wkt_3balls_rejected_by_plausibility():
    """3 wickets in 3 balls (12/3 (0.3)) is impossible at fresh start.
    Per D2 gate (wickets>=2, overs<1.0) → reject.
    """
    sm = _sm()
    card = {"score": 12, "wickets": 3, "overs": 0.3}
    assert sm._cold_start_plausible(card) is False


def test_inn1_severe_collapse_rejected_by_plausibility():
    """8 wickets in 1.2 overs → severe-collapse-implausible reject."""
    sm = _sm()
    card = {"score": 5, "wickets": 8, "overs": 1.2}
    assert sm._cold_start_plausible(card) is False


def test_plausible_card_passes_plausibility():
    """Cold-boot mid-innings 10/0 (2.0) is plausible."""
    sm = _sm()
    card = {"score": 10, "wickets": 0, "overs": 2.0}
    assert sm._cold_start_plausible(card) is True


def test_max_frames_with_implausible_card_defers_and_resets_cold_frames(
        caplog):
    """Drive the max-frames give-up branch with an implausible
    consensus-flip card. State must stay COLD_START and cold_frames
    must reset to 0 (per B1 fix at lines 1278-1285)."""
    sm = _sm()
    impossible = {"score": 12, "wickets": 3, "overs": 0.3}
    plausible_other = {"score": 8, "wickets": 0, "overs": 1.5}

    # Pre-arm: candidate is `plausible_other` with streak=1; flipping
    # to `impossible` triggers the streak-reset branch at line 1253.
    sm.cold_candidate = plausible_other
    sm.cold_candidate_streak = 1
    sm.cold_frames = COLD_MAX_FRAMES  # at the max-frames boundary
    sm.mode = "COLD_START"

    out = sm._handle_cold_start(impossible, _frame())

    # B1 fix postconditions:
    assert out is None
    assert sm.mode == "COLD_START"
    assert sm.cold_frames == 0


def test_max_frames_with_plausible_card_advances_to_warm():
    """Mirror of the above with a plausible card — must commit to WARM."""
    sm = _sm()
    plausible = {"score": 10, "wickets": 0, "overs": 2.0}
    other = {"score": 5, "wickets": 0, "overs": 1.0}

    sm.cold_candidate = other
    sm.cold_candidate_streak = 1
    sm.cold_frames = COLD_MAX_FRAMES
    sm.mode = "COLD_START"

    out = sm._handle_cold_start(plausible, _frame())

    assert sm.mode == "WARM"
    # _build_payload returns a dict with the new state
    assert out is not None
