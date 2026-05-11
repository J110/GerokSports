"""Reproduces the 2026-05-11 TypeError crash where Scorer JSON emitted
score / wickets / overs as strings ("13.5", "110", "3"), and
``_handle_warm`` did ``c_score - self.score`` → TypeError int - str.

Run from repo root:
    pytest files/tests/test_score_manager_type_coerce.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from score_manager import FrameInput, ScoreManager  # noqa: E402


def _make_warm_sm(score: int, wickets: int, overs: float) -> ScoreManager:
    sm = ScoreManager(shadow=False)
    sm.mode = "WARM"
    sm.score, sm.wickets, sm.overs = score, wickets, overs
    return sm


def _frame() -> FrameInput:
    return FrameInput(frame_id="t", timestamp=0.0)


def test_handle_warm_handles_str_overs():
    sm = _make_warm_sm(score=100, wickets=3, overs=13.0)
    card = {"score": "110", "wickets": "4", "overs": "13.5"}
    sm._handle_warm(card, _frame())


def test_handle_warm_handles_str_self_state():
    sm = _make_warm_sm(score=100, wickets=3, overs=13.0)
    sm.score = "100"
    sm.wickets = "3"
    sm.overs = "13.0"
    card = {"score": 101, "wickets": 3, "overs": 13.1}
    sm._handle_warm(card, _frame())


def test_handle_warm_handles_garbage_strings():
    sm = _make_warm_sm(score=50, wickets=1, overs=5.2)
    card = {"score": "n/a", "wickets": "—", "overs": "?"}
    sm._handle_warm(card, _frame())
