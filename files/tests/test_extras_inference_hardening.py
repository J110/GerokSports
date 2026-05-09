"""EXTRAS-inference hardening (Fix A + Fix B).

Fix A: ``ScoreManager._infer_event`` no longer commits an EXTRA event on
overs-lag alone. A hard signal is required:

    * ``broadcast_extra in {"WD", "NB"}``
    * ``extras_total`` digit incremented since prev frame
    * ``d_score == 1`` (vast majority of extras are 1 run)
    * persistent overs-lag (deferral chain hit the 2-frame ceiling)

When none of these are present and the score has jumped without overs
moving, the event is *deferred* — emitted as the
``[EXTRA-INFER-DEFERRED]`` log tag — and the next frame decides. If
overs catch up with the same score delta, the event resolves as a legal
delivery instead.

Fix B: ``_infer_extra``'s text-scan now requires explicit umpire-signal
phrases (``"umpire signals wide"``, ``"called wide by the umpire"``,
``"free hit awarded"`` etc.). Bare substring matches like ``"wide
stance"`` no longer flip the inferred event to WIDE.

Run from repo root:
    pytest files/tests/test_extras_inference_hardening.py -q
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import (  # noqa: E402
    FrameInput,
    ScoreManager,
    _matches_no_ball_signal,
    _matches_wide_signal,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _make_warm_sm(*, score: int, overs: float, wickets: int = 1) -> ScoreManager:
    sm = ScoreManager(shadow=False)
    sb = Scoreboard()
    sb._inn = {
        "score": score, "wickets": wickets, "overs": overs,
        "current_bowler": None, "striker": None, "non": None,
    }
    sb.batting_card = {}
    sb.bowling_card = {}
    sm.scoreboard = sb
    sm.mode = "WARM"
    sm.bat1_name = "A"
    sm.bat2_name = "B"
    sm._cold_pipeline_frames = 100
    return sm


def _frame_mock(**overrides):
    base = dict(
        scorer_changes=[], speed_kph=None, ext_extras_total=None,
        broadcast_extra=None, broadcast_striker=None,
        broadcast_this_over=None, action_text=None,
        delivery_info=None, broadcast_target=None,
        broadcast_venue=None, scout_text="", drs_state="NONE",
        frame_id="F0", timestamp=0.0,
    )
    base.update(overrides)
    return MagicMock(**base)


def _capture(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rv = fn()
    return rv, _ANSI_RE.sub("", buf.getvalue())


# ---------------------------------------------------------------------
# Fix A — hard-signal gating in _infer_event
# ---------------------------------------------------------------------


def test_extra_deferred_when_overs_lags_score():
    """Score jumps +6, overs stuck, no broadcast/umpire signal: the
    event is deferred (no EXTRA committed). When overs catch up on the
    next frame, the event resolves as a legal SIX."""
    sm = _make_warm_sm(score=38, overs=5.5)

    rv1 = sm._handle_warm(
        {"score": 44, "wickets": 1, "overs": 5.5,
         "bat1_name": None, "bat2_name": None, "bowler_name": None},
        _frame_mock(frame_id="F1"))
    assert rv1 is None, "single-frame overs-lag must defer, not commit"
    assert sm.score == 38, "score must stay at baseline while deferred"
    assert sm.last_event is None

    rv2 = sm._handle_warm(
        {"score": 44, "wickets": 1, "overs": 6.0,
         "bat1_name": None, "bat2_name": None, "bowler_name": None},
        _frame_mock(frame_id="F2"))
    assert rv2 is not None
    ev = sm.last_event
    assert ev is not None and ev["type"] != "EXTRA", (
        f"event must resolve as a legal delivery once overs catch up, "
        f"got {ev}")
    assert ev["legal"] is True
    assert ev["runs"] == 6, f"expected SIX, got runs={ev['runs']}"
    assert sm.score == 44


def test_extra_committed_on_broadcast_extra_signal():
    """``broadcast_extra='WD'`` is a hard signal — WIDE commits on the
    first frame even though overs hasn't moved."""
    sm = _make_warm_sm(score=38, overs=5.5)

    rv = sm._handle_warm(
        {"score": 39, "wickets": 1, "overs": 5.5,
         "bat1_name": None, "bat2_name": None, "bowler_name": None,
         "broadcast_extra": "WD"},
        _frame_mock(frame_id="F1", broadcast_extra="WD"))
    assert rv is not None
    ev = sm.last_event
    assert ev is not None
    assert ev["type"] == "WIDE", f"expected WIDE, got {ev['type']}"
    assert ev["this_over_token"] == "Wd"
    assert ev["legal"] is False
    assert sm.score == 39


def test_extra_committed_on_d_score_one_signal():
    """``d_score == 1`` is a hard signal — the event commits as a
    pending EXTRA on the first frame even without broadcast hints."""
    sm = _make_warm_sm(score=38, overs=5.5)

    rv = sm._handle_warm(
        {"score": 39, "wickets": 1, "overs": 5.5,
         "bat1_name": None, "bat2_name": None, "bowler_name": None},
        _frame_mock(frame_id="F1"))
    assert rv is not None
    ev = sm.last_event
    assert ev is not None
    assert ev["type"] == "EXTRA"
    assert ev["runs"] == 1
    assert ev.get("needs_resolution") is True


def test_extra_committed_on_extras_total_bump():
    """``extras_total`` digit incremented across frames is a hard
    signal even when score jumps by > 1."""
    sm = _make_warm_sm(score=38, overs=5.5)
    # Seed prev extras_total via the snapshot path: walk a no-op frame
    # so the SM-side extras dict reflects the broadcast's prior value.
    sm._extras_writable()["total"] = 4

    rv = sm._handle_warm(
        {"score": 40, "wickets": 1, "overs": 5.5,
         "bat1_name": None, "bat2_name": None, "bowler_name": None,
         "extras_total": 6},
        _frame_mock(frame_id="F1", ext_extras_total=6))
    assert rv is not None
    ev = sm.last_event
    assert ev is not None
    assert ev["type"] == "EXTRA"
    assert ev["runs"] == 2


def test_legal_six_with_overs_lag():
    """End-to-end: 38-1(5.5) → 44-1(5.5) [defer] → 44-1(6.0) emits a
    legal SIX, never an EXTRA."""
    sm = _make_warm_sm(score=38, overs=5.5)

    sm._handle_warm(
        {"score": 44, "wickets": 1, "overs": 5.5,
         "bat1_name": None, "bat2_name": None, "bowler_name": None},
        _frame_mock(frame_id="F1"))
    assert sm.last_event is None
    assert sm.score == 38

    sm._handle_warm(
        {"score": 44, "wickets": 1, "overs": 6.0,
         "bat1_name": None, "bat2_name": None, "bowler_name": None},
        _frame_mock(frame_id="F2"))
    assert sm.last_event is not None
    assert sm.last_event["legal"] is True
    assert sm.last_event["runs"] == 6
    assert sm.score == 44


# ---------------------------------------------------------------------
# Fix B — strict umpire-signal text matching
# ---------------------------------------------------------------------


def test_wide_pattern_helpers_reject_naked_wide():
    assert _matches_wide_signal("the batter took a wide stance") is False
    assert _matches_wide_signal("camera switched to a wider angle") is False
    assert _matches_wide_signal("") is False
    assert _matches_wide_signal("umpire signals wide") is True
    assert _matches_wide_signal("called wide by the umpire") is True
    assert _matches_wide_signal("the umpire signalled wide") is True
    # NB pattern in same text suppresses WIDE classification.
    assert _matches_wide_signal(
        "umpire signals wide ... no-ball called") is False


def test_no_ball_pattern_helpers_reject_naked_no_ball():
    assert _matches_no_ball_signal("there is no ball in play") is False
    assert _matches_no_ball_signal("") is False
    assert _matches_no_ball_signal("umpire signals no ball") is True
    assert _matches_no_ball_signal("free hit awarded") is True
    assert _matches_no_ball_signal("no-ball called") is True


def test_wide_classification_requires_umpire_pattern():
    """Scout text contains ``wide stance`` / ``wider angle``: the
    inferred EXTRA must NOT be promoted to WIDE — it stays as a
    generic EXTRA pending resolution."""
    sm = _make_warm_sm(score=38, overs=5.5)
    # Seed recent_frames with text that contains the bare substring
    # "wide" but no umpire signal.
    rf1 = MagicMock(scout_text="batter takes a wide stance at the crease")
    rf2 = MagicMock(scout_text="cut to a wider angle")
    sm.recent_frames = [rf1, rf2]

    frame = _frame_mock(frame_id="F1", scout_text="wider angle")
    event = sm._infer_extra(
        d_score=1, striker="A",
        card={"score": 39, "broadcast_extra": None}, frame=frame)

    assert event["type"] == "EXTRA", (
        f"loose 'wide' substring must not flip type to WIDE; got {event}")
    assert event["this_over_token"] == "1"
    assert event["needs_resolution"] is True
    assert sm.pending_extra is not None


def test_wide_classification_accepted_on_explicit_umpire_signal():
    """Explicit umpire-call text DOES promote the inferred EXTRA to
    WIDE — the strict patterns must still catch real calls."""
    sm = _make_warm_sm(score=38, overs=5.5)
    rf = MagicMock(scout_text="the umpire signals wide")
    sm.recent_frames = [rf]

    event = sm._infer_extra(
        d_score=1, striker="A",
        card={"score": 39, "broadcast_extra": None},
        frame=_frame_mock(frame_id="F1"))

    assert event["type"] == "WIDE"
    assert event["this_over_token"] == "Wd"
    assert event.get("needs_resolution") is False
    assert sm.pending_extra is None


def test_no_ball_classification_accepted_on_free_hit_signal():
    sm = _make_warm_sm(score=38, overs=5.5)
    rf = MagicMock(scout_text="free hit awarded after the no-ball called")
    sm.recent_frames = [rf]

    event = sm._infer_extra(
        d_score=1, striker="A",
        card={"score": 39, "broadcast_extra": None},
        frame=_frame_mock(frame_id="F1"))

    assert event["type"] == "NO_BALL"
    assert event["this_over_token"] == "Nb"
    assert event.get("free_hit_next") is True
    assert event.get("needs_resolution") is False


# ---------------------------------------------------------------------
# Trace tag registration
# ---------------------------------------------------------------------


def test_extra_infer_deferred_tag_is_known():
    from trace_emitter import KNOWN_TAGS
    assert "EXTRA-INFER-DEFERRED" in KNOWN_TAGS


def test_deferred_event_emits_log_tag():
    """The deferred-frame path logs the ``[EXTRA-INFER-DEFERRED]`` tag
    so the analyzer can see how often this guard fires."""
    sm = _make_warm_sm(score=38, overs=5.5)
    # Force an upstream pass-through with no hard signal: capture the
    # log emitted from inside _infer_event when persistent_lag is False
    # and d_score > 1.
    sm._extras_persistent_lag = False
    prev = sm._snapshot()

    _, out = _capture(lambda: sm._infer_event(
        d_score=4, d_wickets=0, d_overs=0.0,
        prev=prev,
        card={"score": prev.get("score", 0) + 4, "broadcast_extra": None},
        frame=_frame_mock(frame_id="F42")))

    assert "[EXTRA-INFER-DEFERRED]" in out, (
        f"expected EXTRA-INFER-DEFERRED tag in log output, got: {out!r}")
    assert "frame=F42" in out
    assert "d_score=4" in out
