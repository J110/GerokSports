"""Fix #23: this_over dedup guard — drop consecutive-frame redelivery
of the same ball.

`ScoreManager._apply_event`'s else-branch (the pad-with-"?" block) used
to unconditionally append `event['this_over_token']` to `self.this_over`
even when `legal_so_far` already met `expected_legal`. A consecutive-
frame redelivery of the same ball (no overs progression, same token)
duplicated the entry. Production trigger: tokens=['W','.','.','1','1']
at overs=3.4 (expected 4 legal). With the guard, the second '1' is
dropped with a `[SM/THIS_OVER] dedup skip` log line.

Run from repo root:
    pytest files/tests/test_this_over_dedup.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import FrameInput, ScoreManager  # noqa: E402


def _make_warm_sm(*, score: int, overs: float,
                  wickets: int = 1) -> ScoreManager:
    sm = ScoreManager(shadow=False)
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C"], ["X", "Y"])
    sb.innings[sb.current_innings].update({
        "score": score, "wickets": wickets, "overs": overs,
        "current_bowler": "X", "striker": "A", "non": "B",
    })
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["B"]["status"] = "batting"
    sm.scoreboard = sb
    sm.mode = "WARM"
    sm.overs = overs
    sm.score = score
    sm.wickets = wickets
    sb._tracker.confirmed["score"] = score
    sb._tracker.confirmed["wickets"] = wickets
    sb._tracker.confirmed["overs"] = overs
    sb._tracker._post_event_grace = 100
    sm.bat1_name = "A"
    sm.bat2_name = "B"
    sm.striker = "A"
    sm.non = "B"
    sm.bowler_name = "X"
    sm._cold_pipeline_frames = 100
    return sm


def _fi() -> FrameInput:
    return FrameInput(frame_id="F0", timestamp=0.0)


def test_this_over_dedup_skips_consecutive_redelivery_of_same_ball():
    sm = _make_warm_sm(score=10, overs=3.4)
    sm.this_over = ['W', '.', '.', '1']
    sm.this_over_src = ['obs', 'obs', 'obs', 'obs']
    prev = {"overs": 3.4, "score": 10}
    card = {"overs": "3.4", "score": 11,
            "bat1_name": "A", "bat2_name": "B", "bowler_name": "X"}

    sm._apply_event(
        {"this_over_token": "1", "legal": True,
         "type": "LEGAL", "runs": 1,
         "striker": "A", "bowler": "X"},
        prev, card, _fi())
    assert sm.this_over == ['W', '.', '.', '1', '1'], (
        f"first apply must append → got {sm.this_over}")

    sm._apply_event(
        {"this_over_token": "1", "legal": True,
         "type": "LEGAL", "runs": 1,
         "striker": "A", "bowler": "X"},
        prev, card, _fi())
    assert sm.this_over == ['W', '.', '.', '1', '1'], (
        f"redelivery of same token must dedup → got {sm.this_over}")


def test_this_over_dedup_allows_different_token():
    sm = _make_warm_sm(score=10, overs=3.4)
    sm.this_over = ['W', '.', '.', '1']
    sm.this_over_src = ['obs', 'obs', 'obs', 'obs']
    prev = {"overs": 3.4, "score": 10}
    card = {"overs": "3.4", "score": 11,
            "bat1_name": "A", "bat2_name": "B", "bowler_name": "X"}

    sm._apply_event(
        {"this_over_token": "1", "legal": True,
         "type": "LEGAL", "runs": 1,
         "striker": "A", "bowler": "X"},
        prev, card, _fi())
    sm._apply_event(
        {"this_over_token": "4", "legal": True,
         "type": "FOUR", "runs": 4,
         "striker": "A", "bowler": "X"},
        prev, card, _fi())
    assert sm.this_over[-2:] == ['1', '4'], (
        f"different incoming token must append (no dedup) → "
        f"got {sm.this_over}")
