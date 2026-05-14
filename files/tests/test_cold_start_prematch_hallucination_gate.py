"""Regression tests for the cold-start pre-match VLM-hallucination gate.

Target: score_manager.py — `_is_skeleton_strip` and `_COLD_START_PREMATCH_CUE`
applied inside `_handle_cold_start` before the consensus accumulator.

Source corpus: `files/logs/deliveries/watch_20260514_102750/scout_raw.jsonl`
F1 (pure skeleton) and F2 (named-player hallucination with toss-narrative).

Run from repo root:
    pytest files/tests/test_cold_start_prematch_hallucination_gate.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from score_manager import (  # noqa: E402
    FrameInput,
    ScoreManager,
    _COLD_START_PREMATCH_CUE,
    _is_skeleton_strip,
)


def _sm() -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm._innings_fallback = 1
    sm._last_warm_state = None
    return sm


def _f1_skeleton() -> FrameInput:
    return FrameInput(
        frame_id="1",
        timestamp=0.0,
        ext_score=1,
        ext_wickets=0,
        ext_overs=0.2,
        ext_bat1_name=None,
        ext_bat2_name=None,
        ext_bowler_name=None,
        scout_text=(
            "VISIBLE_TEXT: KKR  1-0 (0.2)\n"
            "The players are walking onto the field as the team KKR has "
            "won the toss and has chosen to bowl."
        ),
    )


def _f2_named_with_cue() -> FrameInput:
    return FrameInput(
        frame_id="2",
        timestamp=0.0,
        ext_score=1,
        ext_wickets=0,
        ext_overs=0.1,
        ext_bat1_name="Rahul",
        ext_bat2_name="Nissanka",
        ext_bowler_name="Nissanka",
        scout_text=(
            "STRIP: KKR 1-0 (0.1) | *Rahul 1(1) | Nissanka 0(0) | Nissanka 0-1\n"
            "The players are walking out to the field as the team KKR has "
            "won the toss and chose to bowl."
        ),
    )


def _f_real_first_delivery() -> FrameInput:
    return FrameInput(
        frame_id="real",
        timestamp=0.0,
        ext_score=2,
        ext_wickets=0,
        ext_overs=0.3,
        ext_bat1_name="Ajinkya Rahane",
        ext_bat2_name="Angkrish Raghuvanshi",
        ext_bowler_name="Mitchell Starc",
        scout_text=(
            "STRIP: KKR 2-0 (0.3) | *Rahane 1(2) | Raghuvanshi 1(1) | Starc 0-2 (0.3)\n"
            "Starc bowls full to Rahane who taps it to mid-off for a quick single."
        ),
    )


# -- skeleton helper --------------------------------------------------------

def test_skeleton_helper_detects_pure_skeleton_strip():
    assert _is_skeleton_strip(_f1_skeleton()) is True


def test_skeleton_helper_rejects_named_player_strip():
    assert _is_skeleton_strip(_f2_named_with_cue()) is False


def test_skeleton_helper_rejects_real_strip():
    assert _is_skeleton_strip(_f_real_first_delivery()) is False


def test_skeleton_helper_treats_string_null_as_null():
    f = _f1_skeleton()
    f.ext_bat1_name = "null"
    f.ext_bat2_name = ""
    assert _is_skeleton_strip(f) is True


# -- narrative-cue regex ----------------------------------------------------

def test_cue_regex_matches_walking_onto_with_toss():
    text = "The players are walking onto the field as the team KKR has won the toss"
    assert _COLD_START_PREMATCH_CUE.search(text) is not None


def test_cue_regex_matches_walking_out_after_toss():
    text = "The players are walking out to the field after the toss"
    assert _COLD_START_PREMATCH_CUE.search(text) is not None


def test_cue_regex_matches_walking_back():
    assert _COLD_START_PREMATCH_CUE.search(
        "The players are walking back after the toss") is not None


def test_cue_regex_matches_walking_off():
    assert _COLD_START_PREMATCH_CUE.search(
        "The players are walking off the field after the toss") is not None


def test_cue_regex_matches_chose_to_bowl():
    assert _COLD_START_PREMATCH_CUE.search(
        "KKR chose to bowl after winning the toss") is not None


def test_cue_regex_does_not_match_live_delivery_narrative():
    text = (
        "Starc bowls full to Rahane who taps it to mid-off for a quick single."
    )
    assert _COLD_START_PREMATCH_CUE.search(text) is None


# -- _handle_cold_start integration ----------------------------------------

def test_handle_cold_start_rejects_skeleton_and_preserves_budget():
    sm = _sm()
    f1 = _f1_skeleton()
    card = {"score": f1.ext_score, "wickets": f1.ext_wickets,
            "overs": f1.ext_overs}
    cold_frames_before = sm.cold_frames
    out = sm._handle_cold_start(card, f1)
    assert out is None
    assert sm.cold_candidate is None
    assert sm.cold_candidate_streak == 0
    assert sm.cold_frames == cold_frames_before, (
        "skeleton-rejected frames must roll back cold_frames so the "
        "give-up budget is not consumed by hallucinated reads")


def test_handle_cold_start_rejects_cue_and_preserves_budget():
    sm = _sm()
    f2 = _f2_named_with_cue()
    card = {"score": f2.ext_score, "wickets": f2.ext_wickets,
            "overs": f2.ext_overs}
    cold_frames_before = sm.cold_frames
    out = sm._handle_cold_start(card, f2)
    assert out is None
    assert sm.cold_candidate is None
    assert sm.cold_candidate_streak == 0
    assert sm.cold_frames == cold_frames_before


def test_handle_cold_start_accepts_real_strip_after_hallucinations():
    """Replay the F1 / F2 hallucinations then F_real — consensus must
    seed cleanly on the real strip with no carry-over from hallucinated
    candidates."""
    sm = _sm()
    f1, f2, fr = _f1_skeleton(), _f2_named_with_cue(), _f_real_first_delivery()
    for f in (f1, f2):
        card = {"score": f.ext_score, "wickets": f.ext_wickets,
                "overs": f.ext_overs}
        assert sm._handle_cold_start(card, f) is None
    assert sm.cold_candidate is None
    real_card = {
        "score": fr.ext_score, "wickets": fr.ext_wickets, "overs": fr.ext_overs,
    }
    sm._handle_cold_start(real_card, fr)
    # First admitted card seeds the candidate; consensus_streak == 1.
    assert sm.cold_candidate is not None
    assert sm.cold_candidate.get("score") == fr.ext_score
    assert sm.cold_candidate.get("overs") == fr.ext_overs
    assert sm.cold_candidate_streak == 1
