"""Batch AA — BallAnalyzer capture-loop dedupe via frame_count.

Background: BallAnalyzer._capture_loop polls CaptureCardFrameSource's
single-slot get_latest_bgr() unconditionally, faster than the device
emits frames.  Each poll appended (time.time(), bgr) with a fresh wall-
clock timestamp, so compile_frames_to_mp4 saw 4-10× duplicate frames
per real frame and inferred an inflated fps that broke playback timing.
See files/docs/investigations/slow_motion_clip_playback_root_cause.md.

This batch adds a frame-count gate: skip iterations where
self._capture_card.get_frame_count() hasn't advanced since the last
append.  Tests below run the actual BallAnalyzer._capture_loop bound
to a lightweight stub and assert the gate's behavior.

Run from repo root:
    pytest files/tests/test_batch_aa_capture_dedupe.py -q
"""
from __future__ import annotations

import collections
import os
import sys
import threading
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ball_analyzer import BallAnalyzer  # noqa: E402


class _MockCaptureCard:
    """Mirrors CaptureCardFrameSource: count=0 / latest=None until first read."""

    def __init__(self):
        self._count = 0
        self._frame: np.ndarray | None = None

    def advance(self, n: int = 1):
        if self._frame is None:
            self._frame = np.zeros((480, 960, 3), dtype=np.uint8)
        self._count += n

    def get_frame_count(self) -> int:
        return self._count

    def get_latest_bgr(self):
        return self._frame


class _LoopStub:
    """Minimal object with the attributes BallAnalyzer._capture_loop touches."""

    def __init__(self, capture_card: _MockCaptureCard):
        self._running = True
        self._capture_card = capture_card
        self._content_y = 0
        self._frame_buffer: collections.deque = collections.deque(maxlen=4096)
        # ball_analyzer.py:372 added a parallel raw-frame buffer; the
        # capture loop writes both. Stub the second to mirror.
        self._frame_buffer_raw: collections.deque = collections.deque(maxlen=4096)
        self._buf_count = 0
        self._frames_read = 0
        self._actual_fps = 0.0
        self._burst_last_log = time.time()  # suppress 30s log path
        self._tagged_buffer: collections.deque = collections.deque()
        self._tagged_lock = threading.Lock()

    def _grab_full_frame_bgr(self):
        return self._capture_card.get_latest_bgr()


def _run_loop_for(stub: _LoopStub, duration_s: float):
    t = threading.Thread(
        target=BallAnalyzer._capture_loop, args=(stub,), daemon=True)
    t.start()
    time.sleep(duration_s)
    stub._running = False
    t.join(timeout=1.0)
    assert not t.is_alive(), "loop did not exit"


def test_batch_aa_no_duplicate_appends():
    """Static get_frame_count → loop must not append duplicates."""
    cc = _MockCaptureCard()
    cc.advance(1)  # one frame available, count=1
    stub = _LoopStub(cc)

    _run_loop_for(stub, 0.10)

    # Exactly one append for the single produced frame; subsequent
    # iterations see unchanged count and skip.
    assert len(stub._frame_buffer) == 1, (
        f"expected 1 frame appended (count never advanced past 1), "
        f"got {len(stub._frame_buffer)}")


def test_batch_aa_appends_on_new_frames():
    """Each get_frame_count tick → exactly one append."""
    cc = _MockCaptureCard()
    stub = _LoopStub(cc)

    t = threading.Thread(
        target=BallAnalyzer._capture_loop, args=(stub,), daemon=True)
    t.start()
    try:
        for _ in range(5):
            cc.advance(1)
            time.sleep(0.025)  # > 5ms gate sleep, lets loop pick up the tick
    finally:
        stub._running = False
        t.join(timeout=1.0)
    assert not t.is_alive()

    assert len(stub._frame_buffer) == 5, (
        f"expected 5 appends (one per advance), "
        f"got {len(stub._frame_buffer)}")
