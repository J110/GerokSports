"""Tests for llm_rescue.llm_rescue_v_post_gaps.

Run from repo root:
    pytest files/tests/test_llm_rescue.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BMT = os.path.join(ROOT, "scripts", "broadcast_mode_tuning")
for p in (ROOT, BMT):
    if p not in sys.path:
        sys.path.insert(0, p)

from delivery_classifier import FrameInfo  # noqa: E402
from signal_extraction import Signals  # noqa: E402
from llm_rescue import llm_rescue_v_post_gaps  # noqa: E402


def _v_post_frame(t: float, text: str = "bowler ran up") -> FrameInfo:
    s = Signals(V_post=True)
    f = FrameInfo(t=t, text=text, signals=s)
    f.is_delivery = False
    f.path = "none"
    return f


def _idle_frame(t: float, text: str = "players walking") -> FrameInfo:
    f = FrameInfo(t=t, text=text, signals=Signals())
    f.is_delivery = False
    f.path = "none"
    return f


def _kept_cluster(start_t: float, end_t: float | None = None) -> dict:
    if end_t is None:
        end_t = start_t + 1.0
    sig = Signals(V=True, S=True, M=True, W=True, K=True, SS=True, CG=True)
    a = FrameInfo(t=start_t, text="bowler mid-action", signals=sig)
    a.is_delivery, a.path = True, "B"
    b = FrameInfo(t=end_t, text="batter swung", signals=sig)
    b.is_delivery, b.path = True, "B"
    return {
        "start_t": start_t,
        "end_t": end_t,
        "anchor_t": start_t,
        "anchor": a,
        "frames": [a, b],
    }


class _Counter:
    def __init__(self, response: dict):
        self.calls = 0
        self.response = response
        self.last_prose: str = ""

    def __call__(self, prose: str) -> dict:
        self.calls += 1
        self.last_prose = prose
        return dict(self.response)


def test_no_gap_skip():
    """Adjacent clusters with no real gap → no LLM call."""
    clusters = [_kept_cluster(100.0), _kept_cluster(110.0)]
    frames = [_v_post_frame(t) for t in (102.0, 104.0, 106.0, 108.0)]
    caller = _Counter({"delivery_found": True, "approx_t": 105.0,
                       "confidence": "high", "reason": "x"})
    out = llm_rescue_v_post_gaps(clusters, frames, llm_caller=caller)
    assert caller.calls == 0
    assert not any(c.get("rescued_by") == "llm_v_post_gap" for c in out)


def test_gap_with_no_v_post_skip():
    """Gap big enough but no V_post frames inside → no LLM call."""
    clusters = [_kept_cluster(100.0), _kept_cluster(200.0)]
    frames = [_idle_frame(t) for t in (130.0, 140.0, 150.0, 160.0, 170.0)]
    caller = _Counter({"delivery_found": True, "approx_t": 150.0,
                       "confidence": "high", "reason": "x"})
    out = llm_rescue_v_post_gaps(clusters, frames, llm_caller=caller)
    assert caller.calls == 0
    assert not any(c.get("rescued_by") == "llm_v_post_gap" for c in out)


def test_gap_with_three_v_post_rescues_nearest_to_approx_t():
    """Gap with >=3 V_post + LLM high-confidence yes → rescued cluster
    at the V_post frame nearest approx_t."""
    clusters = [_kept_cluster(100.0, 101.0), _kept_cluster(200.0, 201.0)]
    frames = [_v_post_frame(t) for t in (130.0, 145.0, 160.0)]
    # Returns absolute t in mid of gap; closest V_post = t=145.0.
    caller = _Counter({"delivery_found": True, "approx_t": 144.0,
                       "confidence": "high",
                       "reason": "bowler released ball at t=144"})
    out = llm_rescue_v_post_gaps(clusters, frames, llm_caller=caller)
    assert caller.calls == 1
    rescued = [c for c in out if c.get("rescued_by") == "llm_v_post_gap"]
    assert len(rescued) == 1
    assert rescued[0]["start_t"] == 145.0
    assert rescued[0]["frames"][0].t == 145.0
    assert rescued[0]["llm_confidence"] == "high"
    # Output stays sorted by start_t.
    starts = [c["start_t"] for c in out]
    assert starts == sorted(starts)


def test_llm_says_no_delivery_no_rescue():
    """LLM returns delivery_found=false → no rescue."""
    clusters = [_kept_cluster(100.0, 101.0), _kept_cluster(200.0, 201.0)]
    frames = [_v_post_frame(t) for t in (130.0, 145.0, 160.0)]
    caller = _Counter({"delivery_found": False, "approx_t": None,
                       "confidence": "high",
                       "reason": "no active play"})
    out = llm_rescue_v_post_gaps(clusters, frames, llm_caller=caller)
    assert caller.calls == 1
    assert not any(c.get("rescued_by") == "llm_v_post_gap" for c in out)


def test_low_confidence_no_rescue():
    """LLM confidence=low → no rescue even if delivery_found=true."""
    clusters = [_kept_cluster(100.0, 101.0), _kept_cluster(200.0, 201.0)]
    frames = [_v_post_frame(t) for t in (130.0, 145.0, 160.0)]
    caller = _Counter({"delivery_found": True, "approx_t": 145.0,
                       "confidence": "low",
                       "reason": "ambiguous frames"})
    out = llm_rescue_v_post_gaps(clusters, frames, llm_caller=caller)
    assert caller.calls == 1
    assert not any(c.get("rescued_by") == "llm_v_post_gap" for c in out)


def test_cost_cap_at_max_calls():
    """11 qualifying gaps → only 10 LLM calls; 11th gap untouched."""
    # Build 12 kept clusters spaced 100s apart → 11 gaps of ~99s.
    clusters = [_kept_cluster(t * 100.0, t * 100.0 + 1.0)
                for t in range(1, 13)]
    # Each gap needs >=3 V_post frames inside.
    frames: list[FrameInfo] = []
    for i in range(11):
        gap_start = clusters[i]["end_t"]
        for offset in (10.0, 25.0, 40.0):
            frames.append(_v_post_frame(gap_start + offset))
    caller = _Counter({"delivery_found": False, "approx_t": None,
                       "confidence": "high", "reason": "x"})
    llm_rescue_v_post_gaps(clusters, frames, llm_caller=caller)
    assert caller.calls == 10


def test_relative_approx_t_resolves_to_absolute():
    """Model returns approx_t as offset from window start (e.g. 15)
    rather than absolute (115). It should resolve to the nearest V_post
    inside the gap."""
    clusters = [_kept_cluster(100.0, 101.0), _kept_cluster(200.0, 201.0)]
    frames = [_v_post_frame(t) for t in (115.0, 145.0, 175.0)]
    # 15 → gap_lo (101) + 15 = 116 → nearest V_post = 115.
    caller = _Counter({"delivery_found": True, "approx_t": 15.0,
                       "confidence": "medium", "reason": "early in window"})
    out = llm_rescue_v_post_gaps(clusters, frames, llm_caller=caller)
    rescued = [c for c in out if c.get("rescued_by") == "llm_v_post_gap"]
    assert len(rescued) == 1
    assert rescued[0]["start_t"] == 115.0
