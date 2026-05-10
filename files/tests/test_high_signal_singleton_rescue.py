"""Tests for rescue_high_signal_singletons (P2).

Run from repo root:
    pytest files/tests/test_high_signal_singleton_rescue.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BMT = os.path.join(ROOT, "scripts", "broadcast_mode_tuning")
for p in (ROOT, BMT):
    if p not in sys.path:
        sys.path.insert(0, p)

from delivery_classifier import (  # noqa: E402
    FrameInfo, rescue_high_signal_singletons,
)
from signal_extraction import Signals  # noqa: E402


def _frame(t: float, path: str, signals: Signals,
           text: str = "") -> FrameInfo:
    f = FrameInfo(t=t, text=text, signals=signals)
    f.is_delivery = path in ("A", "B", "C", "D")
    f.path = path
    return f


def _kept_cluster(anchor_t: float, path: str = "B") -> dict:
    sig = Signals(V=True, S=True, M=True, M2=True, W=True, K=True,
                  SS=True, CG=True)
    a = _frame(anchor_t, path, sig)
    b = _frame(anchor_t + 1.0, path, sig)
    return {
        "start_t": anchor_t,
        "end_t": anchor_t + 1.0,
        "anchor_t": anchor_t,
        "anchor": a,
        "frames": [a, b],
    }


def _high_sig_signals(n: int) -> Signals:
    """Return a Signals object with exactly n of the 9 tracked flags set."""
    flags = ["V", "V_post", "S", "M", "M2", "W", "K", "SS", "CG"]
    s = Signals()
    for f in flags[:n]:
        setattr(s, f, True)
    return s


def test_rescues_path_b_with_8_signals_isolated():
    kept = [_kept_cluster(100.0), _kept_cluster(200.0)]
    orphan = _frame(150.0, "B", _high_sig_signals(8))
    out = rescue_high_signal_singletons(kept, [orphan])
    rescued = [c for c in out if c.get("high_signal_rescued")]
    assert len(rescued) == 1
    assert rescued[0]["frames"][0].t == 150.0
    assert rescued[0]["rescue_signal_count"] == 8


def test_does_not_rescue_below_signal_threshold():
    kept = [_kept_cluster(100.0), _kept_cluster(200.0)]
    orphan = _frame(150.0, "B", _high_sig_signals(7))
    out = rescue_high_signal_singletons(kept, [orphan])
    assert not any(c.get("high_signal_rescued") for c in out)


def test_does_not_rescue_when_too_close_to_kept_anchor():
    kept = [_kept_cluster(100.0), _kept_cluster(200.0)]
    # 10s away from kept anchor at 100.0 — under 30s default
    orphan = _frame(110.0, "A", _high_sig_signals(9))
    out = rescue_high_signal_singletons(kept, [orphan])
    assert not any(c.get("high_signal_rescued") for c in out)


def test_does_not_rescue_path_c_singleton():
    kept = [_kept_cluster(100.0), _kept_cluster(200.0)]
    orphan = _frame(150.0, "C", _high_sig_signals(8))
    out = rescue_high_signal_singletons(kept, [orphan])
    assert not any(c.get("high_signal_rescued") for c in out)


def test_does_not_rescue_when_hard_reject_within_2s():
    kept = [_kept_cluster(100.0), _kept_cluster(200.0)]
    orphan = _frame(150.0, "B", _high_sig_signals(8))
    hard_sig = Signals(HARD=True)
    hard_neighbor = _frame(151.5, "none", hard_sig)
    hard_neighbor.is_delivery = False
    out = rescue_high_signal_singletons(kept, [orphan, hard_neighbor])
    assert not any(c.get("high_signal_rescued") for c in out)


def test_rescues_path_d_with_high_signals():
    kept = [_kept_cluster(100.0), _kept_cluster(200.0)]
    orphan = _frame(150.0, "D", _high_sig_signals(8))
    out = rescue_high_signal_singletons(kept, [orphan])
    rescued = [c for c in out if c.get("high_signal_rescued")]
    assert len(rescued) == 1
    assert rescued[0]["frames"][0].path == "D"


def test_rescued_clusters_sorted_with_kept():
    kept = [_kept_cluster(100.0), _kept_cluster(300.0)]
    orphan = _frame(200.0, "B", _high_sig_signals(8))
    out = rescue_high_signal_singletons(kept, [orphan])
    starts = [c["start_t"] for c in out]
    assert starts == sorted(starts)
    assert 200.0 in starts
