"""D7 batting_team N-frame consensus tests.

`_detect_innings_change` now requires the same new team to be observed
on N consecutive frames before flipping batting_team / firing the inn-2
trigger. Single-frame pre-match-graphic flips no longer commit.

Run from repo root:
    pytest files/tests/test_team_change_consensus.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from score_manager import FrameInput, ScoreManager  # noqa: E402


def _frame(team: str | None) -> FrameInput:
    return FrameInput(
        frame_id="f", timestamp=0.0, broadcast_team=team)


def _sm_warm_with_team(team: str) -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm.mode = "WARM"
    sm._innings_fallback = 1
    sm._sm_scalar_fallback["batting_team"] = team
    return sm


def _detect(sm: ScoreManager, team: str | None) -> bool:
    return sm._detect_innings_change({}, _frame(team))


def test_one_frame_different_team_no_change():
    sm = _sm_warm_with_team("GT")
    assert _detect(sm, "CSK") is False
    assert sm._team_change_candidate == "CSK"
    assert sm._team_change_streak == 1


def test_two_frames_different_team_no_change():
    sm = _sm_warm_with_team("GT")
    _detect(sm, "CSK")
    assert _detect(sm, "CSK") is False
    assert sm._team_change_streak == 2


def test_three_frames_different_team_fires_change():
    sm = _sm_warm_with_team("GT")
    _detect(sm, "CSK")
    _detect(sm, "CSK")
    assert _detect(sm, "CSK") is True
    assert sm._team_change_candidate is None
    assert sm._team_change_streak == 0


def test_current_team_resets_candidate():
    sm = _sm_warm_with_team("GT")
    _detect(sm, "CSK")
    assert sm._team_change_streak == 1
    assert _detect(sm, "GT") is False
    assert sm._team_change_candidate is None
    assert sm._team_change_streak == 0


def test_different_then_other_different_resets_streak():
    sm = _sm_warm_with_team("GT")
    _detect(sm, "CSK")
    _detect(sm, "MI")
    assert sm._team_change_candidate == "MI"
    assert sm._team_change_streak == 1
    assert _detect(sm, "CSK") is False
    assert sm._team_change_candidate == "CSK"
    assert sm._team_change_streak == 1
