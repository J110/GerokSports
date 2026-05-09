"""P3 — replay/recap-inset detector (Mode-C + N-frame debounce).

See files/docs/investigations/replay_inset_detection_diagnosis.md.

Run: pytest files/tests/test_recap_inset_detection.py -q
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from test_pipeline import (  # noqa: E402
    OVERLAY_WINDOW_FRAMES,
    _detect_recap_inset_mode_c,
    _poison_scoreboard_after_graphic_transition,
    _should_poison_in_overlay_window,
)


# ── Mode-C trigger ────────────────────────────────────────────────


def test_mode_c_cold_start_no_trigger() -> None:
    """F8-class true cold-start: tracker not committed, Mode-C must NOT
    fire (P12 owns this hole per the diagnosis §6).
    """
    triggered, reason = _detect_recap_inset_mode_c(
        extracted_score=47,
        extracted_team=None,
        scout_strip_text="STRIP: null 47-3 (7.5)",
        tracker_score=None,
        tracker_state_committed=False,
    )
    assert triggered is False
    assert reason is None


def test_mode_c_mid_innings_team_null_delta_triggers() -> None:
    """F94-class: tracker committed at MI 1-1, strip reads null 47-3 →
    delta=46 (>10) and team=null → Mode-C fires via team_null_delta.
    """
    triggered, reason = _detect_recap_inset_mode_c(
        extracted_score=47,
        extracted_team=None,
        scout_strip_text="STRIP: null 47-3 (7.5)",
        tracker_score=1,
        tracker_state_committed=True,
    )
    assert triggered is True
    assert reason is not None and reason.startswith("team_null_delta_")


def test_mode_c_49_3_phantom_triggers() -> None:
    """F235-class: same pattern with 49-3, large delta vs tracker."""
    triggered, reason = _detect_recap_inset_mode_c(
        extracted_score=49,
        extracted_team=None,
        scout_strip_text="STRIP: null 49-3 (7.5)",
        tracker_score=80,
        tracker_state_committed=True,
    )
    assert triggered is True
    assert reason == "team_null_delta_31"


def test_mode_c_team_present_no_delta_trigger() -> None:
    """A real strip with `MI` prefix should never trigger via path 1
    even if the score delta is large (handled by other guards).
    """
    triggered, _reason = _detect_recap_inset_mode_c(
        extracted_score=200,
        extracted_team="MI",
        scout_strip_text="STRIP: MI 200-3 (15.0)",
        tracker_score=10,
        tracker_state_committed=True,
    )
    assert triggered is False


def test_mode_c_small_delta_no_trigger() -> None:
    """team=null with score within threshold → not the recap inset."""
    triggered, _reason = _detect_recap_inset_mode_c(
        extracted_score=45,
        extracted_team=None,
        scout_strip_text="STRIP: null 45-3 (7.0)",
        tracker_score=42,
        tracker_state_committed=True,
        score_delta_threshold=10,
    )
    assert triggered is False


def test_mode_c_fingerprint_path_triggers_at_cold_start() -> None:
    """Trigger 2 (fingerprint) is independent of the tracker —
    operator-supplied regex catches the F8 cold-start phantom.
    """
    fp = re.compile(r"\b47-3\b")
    triggered, reason = _detect_recap_inset_mode_c(
        extracted_score=47,
        extracted_team=None,
        scout_strip_text="STRIP: Chennai Super Kings 47-3 (7.5)",
        tracker_score=None,
        tracker_state_committed=False,
        fingerprint_re=fp,
    )
    assert triggered is True
    assert reason == "fingerprint"


def test_mode_c_fingerprint_no_match_no_trigger() -> None:
    fp = re.compile(r"\b47-3\b")
    triggered, _reason = _detect_recap_inset_mode_c(
        extracted_score=120,
        extracted_team="MI",
        scout_strip_text="STRIP: MI 120-2 (15.4)",
        tracker_score=120,
        tracker_state_committed=True,
        fingerprint_re=fp,
    )
    assert triggered is False


# ── N-frame debounce ──────────────────────────────────────────────


def test_overlay_window_default_matches_env_default() -> None:
    """Sanity: the in-process default window is the spec's K=5 (or
    whatever the operator set OVERLAY_WINDOW_FRAMES to).
    """
    assert OVERLAY_WINDOW_FRAMES >= 1


def test_debounce_active_with_team_null_scoreboard() -> None:
    assert _should_poison_in_overlay_window(
        overlay_window_remaining=4,
        frame_type="SCOREBOARD",
        extracted_team=None,
    )


def test_debounce_inactive_when_window_expired() -> None:
    assert not _should_poison_in_overlay_window(
        overlay_window_remaining=0,
        frame_type="SCOREBOARD",
        extracted_team=None,
    )


def test_debounce_inactive_when_team_present() -> None:
    """A real strip read inside the window (team prefix present) is
    treated as recovered live state and bypasses the debounce."""
    assert not _should_poison_in_overlay_window(
        overlay_window_remaining=3,
        frame_type="SCOREBOARD",
        extracted_team="MI",
    )


def test_debounce_inactive_on_non_scoreboard_frame() -> None:
    """GRAPHIC frames are handled by Mode A; the debounce only covers
    SCOREBOARD-tagged frames in the post-firing tail.
    """
    assert not _should_poison_in_overlay_window(
        overlay_window_remaining=3,
        frame_type="GRAPHIC",
        extracted_team=None,
    )


def test_debounce_window_simulated_decrement_to_zero() -> None:
    """Simulate the per-frame decrement: K=5 → 4 protected frames
    after firing (start-of-frame decrement, then check). The 5th
    follow-up frame sees remaining=0 and is not poisoned.
    """
    K = 5
    remaining = K  # set by Mode-C firing in frame N
    poisoned_followups: list[bool] = []
    for _follow_idx in range(K + 1):
        if remaining > 0:
            remaining -= 1
        poisoned_followups.append(
            _should_poison_in_overlay_window(
                overlay_window_remaining=remaining,
                frame_type="SCOREBOARD",
                extracted_team=None,
            ))
    # Frames N+1..N+K-1 are protected (K-1 = 4); frame N+K is not.
    assert poisoned_followups[: K - 1] == [True] * (K - 1)
    assert poisoned_followups[K - 1] is False


# ── Mode A/B regression (P2 still functions) ──────────────────────


def test_mode_b_graphic_to_scoreboard_still_fires() -> None:
    assert _poison_scoreboard_after_graphic_transition(
        prev_vision_frame_type="GRAPHIC",
        frame_type="SCOREBOARD",
        already_poisoned=False,
    )


def test_mode_b_no_double_poison() -> None:
    assert not _poison_scoreboard_after_graphic_transition(
        prev_vision_frame_type="GRAPHIC",
        frame_type="SCOREBOARD",
        already_poisoned=True,
    )
