"""Smoke-test DeliveryWindowRecorder with synthetic Scout tags.

Verifies the state machine behaviour without touching the live capture
loop:

  Test A: Normal close on dead view (replay).
  Test B: Close on score event (RECORDING -> CLASSIFYING -> IDLE).
  Test C: Close on max-window timeout.
  Test D: Brief gap (1s closeup) tolerated; window stays open.
  Test E: No bowlers_end ever -> score event returns None.

For Test A & B we feed real frames from ball_test_clip_30fps.mp4 so
the Gemini call actually runs end-to-end.  C, D, E use a stub
classifier to avoid extra Gemini spend.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from delivery_window_recorder import (
    DeliveryWindowRecorder,
    BACKFILL_S, GAP_TOLERANCE_S, MAX_WINDOW_S, MIN_WINDOW_S, TAIL_S,
)
from gemini_delivery_classifier import GeminiDeliveryClassifier


# ── Stub classifier (no network) ────────────────────────────────

class StubClassifier:
    def __init__(self):
        self.calls = []

    def classify_frames(self, frames, runs=0, save_dir=None, **kw):
        self.calls.append({"n_frames": len(frames), "runs": runs})
        return {
            "_method": "stub",
            "length": "good_length",
            "line": "outside_off",
            "bowling_angle": "over",
            "bounce": "normal",
            "shot_type": "along_ground",
            "shot_action": "drive",
            "shot_intent": "attacked",
            "shot_direction": {"side": "off", "zone": "mid",
                               "confidence": "medium"},
            "shot_elevation": "along_ground",
            "swing_or_seam": "not_visible",
            "batsman_handed": "right",
            "bowling_arm": "right",
            "bowling_type": "fast",
            "contact_quality": "middled",
            "narrative": "stub narrative",
            "commentary_line": "stub commentary",
            "_gemini_confidence": "medium",
        }


# ── Real frames source (clip 1) ─────────────────────────────────

def _load_clip_frames(path: Path,
                      target_fps: float = 20.0) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or target_fps
    stride = max(1, int(round(src_fps / target_fps)))
    frames: list[np.ndarray] = []
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % stride == 0:
            frames.append(fr)
        i += 1
    cap.release()
    return frames


CLIP1 = ROOT / "ball_test_clip_30fps.mp4"
_CLIP_FRAMES_CACHE: list[np.ndarray] | None = None


def _make_frame_source(t0: float, frames: list[np.ndarray],
                       fps: float = 20.0):
    """Return a frame_source_fn(start_ts, end_ts) -> [(ts, frame)].

    Maps the recorded clip onto a synthetic timeline starting at t0,
    one frame per 1/fps second.
    """
    def fn(start_ts: float, end_ts: float):
        out = []
        for i, fr in enumerate(frames):
            ts = t0 + i / fps
            if start_ts <= ts <= end_ts:
                out.append((ts, fr))
        return out
    return fn


# ── Helpers ────────────────────────────────────────────────────

def feed(rec, ts, view):
    print(f"  [{ts:6.2f}] tag {view!r:>14}", flush=True)
    rec.on_scout_tag(ts, view)


def banner(name):
    print(f"\n{'=' * 72}\nTEST {name}\n{'=' * 72}")


def assert_eq(name, got, want):
    ok = got == want
    print(f"  {'OK ' if ok else 'XX '} {name}: got={got!r} want={want!r}")
    return ok


# ── Tests ──────────────────────────────────────────────────────

def test_a_close_on_dead_view(real_clf):
    banner("A — close on dead_view (real Gemini call)")
    global _CLIP_FRAMES_CACHE
    if _CLIP_FRAMES_CACHE is None:
        _CLIP_FRAMES_CACHE = _load_clip_frames(CLIP1)
    frames = _CLIP_FRAMES_CACHE
    print(f"  loaded {len(frames)} frames from {CLIP1.name}")

    t0 = 1000.0
    src = _make_frame_source(t0, frames, fps=20.0)
    save_dir = ROOT / "logs" / "dwr_smoke" / "test_a"
    save_dir.mkdir(parents=True, exist_ok=True)
    rec = DeliveryWindowRecorder(real_clf, src, save_root=save_dir)

    feed(rec, t0 + 1.0, "bowlers_end")        # OPEN
    feed(rec, t0 + 4.0, "bowlers_end")        # extend
    feed(rec, t0 + 6.0, "bowlers_end")        # extend
    feed(rec, t0 + 8.0, "replay")             # CLOSE -> CLASSIFYING

    print("  awaiting classifier ...")
    res = rec.classify_for_score_event(
        runs=0, event_type="DOT", await_timeout_s=60.0)
    print(f"  result: keys={sorted((res or {}).keys())[:8]}")
    if res:
        print(f"    handedness={res.get('batsman_handed')} "
              f"len={res.get('length')} line={res.get('line')} "
              f"shot={res.get('shot_action')} "
              f"narrative={res.get('narrative','')[:80]!r}")

    rec.shutdown()
    return res is not None and res.get("_method") == "gemini"


def test_b_close_on_score(stub):
    banner("B — close on score event (stub classifier)")
    t0 = 0.0
    src = _make_frame_source(t0, [np.zeros((100, 160, 3), dtype=np.uint8)
                                   for _ in range(200)], fps=20.0)
    rec = DeliveryWindowRecorder(stub, src)

    feed(rec, 1.0, "bowlers_end")
    feed(rec, 3.0, "bowlers_end")
    feed(rec, 5.0, "bowlers_end")

    print("  triggering score_event at t=6.0")
    res = rec.classify_for_score_event(runs=4, event_type="FOUR",
                                       await_timeout_s=5.0)
    rec.shutdown()
    if not res:
        print("  XX no result")
        return False
    return (assert_eq("method", res.get("_method"), "stub")
            and assert_eq("runs",   res.get("runs"), 4)
            and assert_eq("event",  res.get("_event_type"), "FOUR"))


def test_c_timeout(stub):
    banner("C — close on MAX_WINDOW_S timeout (stub)")
    t0 = 0.0
    src = _make_frame_source(t0, [np.zeros((100, 160, 3), dtype=np.uint8)
                                   for _ in range(int(MAX_WINDOW_S * 25))],
                             fps=20.0)
    rec = DeliveryWindowRecorder(stub, src)
    feed(rec, 1.0, "bowlers_end")  # OPEN, delivery_start_ts = -1.0
    # Keep tagging bowlers_end through the window — extends but does
    # NOT reset delivery_start_ts.  No further tags after t=20 so the
    # timeout fires cleanly without a fresh window opening behind it.
    for t in [3, 6, 9, 12, 15, 18, 20]:
        feed(rec, float(t), "bowlers_end")
    rec.tick(now=24.5)  # 24.5 - (-1.0) = 25.5 >= 25.0 -> timeout
    # Wait briefly for the stub to complete in the executor pool.
    time.sleep(0.2)
    res = rec.classify_for_score_event(
        runs=0, event_type="DOT", await_timeout_s=5.0)
    rec.shutdown()
    if not res:
        print("  XX no result")
        return False
    print(f"  window_reason={res.get('_window_reason')!r}")
    return assert_eq("window_reason starts_with timeout",
                     str(res.get("_window_reason", "")).startswith("timeout"),
                     True)


def test_d_brief_gap_tolerated(stub):
    banner("D — brief gap (closeup 1s) tolerated, window stays open")
    t0 = 0.0
    frames = [np.zeros((100, 160, 3), dtype=np.uint8) for _ in range(400)]
    src = _make_frame_source(t0, frames, fps=20.0)
    rec = DeliveryWindowRecorder(stub, src,
                                 gap_tolerance_s=GAP_TOLERANCE_S)
    feed(rec, 1.0, "bowlers_end")     # OPEN
    feed(rec, 3.0, "bowlers_end")
    feed(rec, 4.0, "side_on")         # gap starts (not in DEAD_VIEWS)
    feed(rec, 4.5, "side_on")         # 1.5 s gap, < 2 s
    feed(rec, 5.0, "bowlers_end")     # gap reset
    feed(rec, 7.0, "bowlers_end")
    print("  state should still be RECORDING:", rec._state)
    if rec._state != "RECORDING":
        print("  XX expected RECORDING, got", rec._state)
        rec.shutdown()
        return False
    feed(rec, 9.0, "replay")          # CLOSE
    res = rec.classify_for_score_event(
        runs=1, event_type="RUNS", await_timeout_s=5.0)
    rec.shutdown()
    return res is not None


def test_e_no_bowlers_end(stub):
    banner("E — no bowlers_end ever — score event returns None")
    t0 = 0.0
    frames = [np.zeros((100, 160, 3), dtype=np.uint8) for _ in range(20)]
    src = _make_frame_source(t0, frames, fps=20.0)
    rec = DeliveryWindowRecorder(stub, src)
    for t in [1, 2, 3, 4, 5]:
        feed(rec, float(t), "side_on")
    res = rec.classify_for_score_event(
        runs=0, event_type="DOT", await_timeout_s=2.0)
    rec.shutdown()
    return assert_eq("no result", res, None)


def main():
    stub = StubClassifier()
    real = GeminiDeliveryClassifier()
    if not real.available():
        print(f"FATAL: real classifier unavailable: {real._init_error}")
        sys.exit(1)

    results = {
        "A": test_a_close_on_dead_view(real),
        "B": test_b_close_on_score(stub),
        "C": test_c_timeout(stub),
        "D": test_d_brief_gap_tolerated(stub),
        "E": test_e_no_bowlers_end(stub),
    }
    print(f"\n{'=' * 72}\nSUMMARY")
    for k, ok in results.items():
        print(f"  {k}: {'PASS' if ok else 'FAIL'}")
    if not all(results.values()):
        sys.exit(2)


if __name__ == "__main__":
    main()
