"""BallAnalyzer file-replay capture path.

Verifies the third capture branch added alongside ``_capture_card`` and
the Quartz fallback: when ``_file_frame_source`` is set,
``_grab_full_frame_bgr`` pulls frames from it and the capture loop
populates ``_frame_buffer_raw`` / ``_frame_source`` correctly.

Pattern mirrors ``test_batch_aa_capture_dedupe.py``: drive
``BallAnalyzer._capture_loop`` against a stub so the test does not have
to instantiate the full analyzer (Gemini, span aggregator, etc.).
"""
from __future__ import annotations

import collections
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

cv2 = pytest.importorskip("cv2")

from ball_analyzer import BallAnalyzer  # noqa: E402
from eyes.capture.frame_source import FileFrameSource  # noqa: E402


def _write_mp4(path: Path, n_frames: int, fps: int,
               size: tuple[int, int] = (320, 240)) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, float(fps), size)
    if not writer.isOpened():
        pytest.skip(f"cv2.VideoWriter could not open {path}")
    w, h = size
    for i in range(n_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        v = (i * 7) % 256
        frame[:, :] = (v, v, v)
        writer.write(frame)
    writer.release()


class _LoopStub:
    """Minimal object exposing the attributes BallAnalyzer._capture_loop
    touches.  Wraps an active FileFrameSource via the same interface
    BallAnalyzer uses in production."""

    def __init__(self, file_frame_source: FileFrameSource):
        self._running = True
        self._capture_card = None
        self._file_frame_source = file_frame_source
        self._content_y = 0
        self._frame_buffer: collections.deque = collections.deque(maxlen=4096)
        self._frame_buffer_raw: collections.deque = collections.deque(
            maxlen=4096)
        self._buf_count = 0
        self._frames_read = 0
        self._actual_fps = 0.0
        self._burst_last_log = time.time()
        self._tagged_buffer: collections.deque = collections.deque()
        self._tagged_lock = threading.Lock()

    def _grab_full_frame_bgr(self):
        return BallAnalyzer._grab_full_frame_bgr(self)

    def _frame_source(self, start_ts: float, end_ts: float):
        return [(ts, fr) for ts, fr in list(self._frame_buffer_raw)
                if start_ts <= ts <= end_ts]


def _run_loop(stub: _LoopStub, duration_s: float) -> None:
    t = threading.Thread(
        target=BallAnalyzer._capture_loop, args=(stub,), daemon=True)
    t.start()
    time.sleep(duration_s)
    stub._running = False
    t.join(timeout=2.0)
    assert not t.is_alive(), "capture loop did not exit"


def test_frame_buffer_raw_populates_in_file_mode(tmp_path: Path):
    """File-mode capture path lands frames in _frame_buffer_raw."""
    p = tmp_path / "replay.mp4"
    _write_mp4(p, n_frames=60, fps=25)
    src = FileFrameSource(video_path=p)
    src.start()
    try:
        stub = _LoopStub(src)
        _run_loop(stub, 2.0)
        assert len(stub._frame_buffer_raw) > 0, (
            "_frame_buffer_raw stayed empty in file mode — "
            "_grab_full_frame_bgr did not pull from FileFrameSource")
        for ts, fr in list(stub._frame_buffer_raw):
            assert fr is not None
            assert fr.ndim == 3 and fr.shape[2] == 3
            assert ts > 0
    finally:
        src.stop()


def test_frame_source_slice_returns_frames(tmp_path: Path):
    """_frame_source(start_ts, end_ts) returns a non-empty slice for
    a window inside the recorded interval, with all timestamps in
    range."""
    p = tmp_path / "slice.mp4"
    _write_mp4(p, n_frames=25 * 6, fps=25)
    src = FileFrameSource(video_path=p)
    src.start()
    try:
        stub = _LoopStub(src)
        capture_t0 = time.time()
        _run_loop(stub, 5.0)
        capture_t1 = time.time()

        start_ts = capture_t0 + 1.0
        end_ts = capture_t1 - 1.0
        assert end_ts > start_ts

        sliced = stub._frame_source(start_ts, end_ts)
        assert len(sliced) > 0, (
            f"_frame_source returned empty slice for window "
            f"[{start_ts}, {end_ts}] over buffer of "
            f"{len(stub._frame_buffer_raw)} frames")
        for ts, fr in sliced:
            assert start_ts <= ts <= end_ts, (
                f"sliced frame ts {ts} outside requested window "
                f"[{start_ts}, {end_ts}]")
            assert fr is not None
    finally:
        src.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
