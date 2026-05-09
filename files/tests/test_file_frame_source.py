"""Tests for ``FileFrameSource`` (offline mp4 replay).

Each test builds its own throwaway mp4 with cv2 so the suite has no
binary fixture dependency. Pacing checks use generous tolerances —
sleep accounting is best-effort across CI hardware.

Run from repo root:
    pytest files/tests/test_file_frame_source.py -q
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

cv2 = pytest.importorskip("cv2")

from eyes.capture.frame_source import (  # noqa: E402
    FileFrameSource,
    make_frame_source,
)


def _write_mp4(path: Path, n_frames: int, fps: int,
               size: tuple[int, int] = (160, 120)) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, float(fps), size)
    if not writer.isOpened():
        pytest.skip(f"cv2.VideoWriter could not open {path} (codec missing)")
    w, h = size
    for i in range(n_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # Encode the frame index in a corner block so reads can be
        # identified positionally.
        val = (i * 7) % 256
        frame[:, :] = (val, val, val)
        writer.write(frame)
    writer.release()


@pytest.fixture
def short_mp4(tmp_path: Path) -> Path:
    p = tmp_path / "short.mp4"
    _write_mp4(p, n_frames=10, fps=25)
    return p


@pytest.fixture
def long_mp4(tmp_path: Path) -> Path:
    # 15s @ 25fps so a 10s seek leaves ~5s of frames behind.
    p = tmp_path / "long.mp4"
    _write_mp4(p, n_frames=25 * 15, fps=25)
    return p


def _wait_for_frame(src: FileFrameSource, timeout_s: float = 2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        f = src.get_latest_bgr()
        if f is not None:
            return f
        time.sleep(0.01)
    return None


def test_opens_mp4_and_reads_frames(short_mp4: Path):
    src = FileFrameSource(video_path=short_mp4)
    src.start()
    try:
        frame = _wait_for_frame(src)
        assert frame is not None
        assert frame.ndim == 3 and frame.shape[2] == 3
        assert src.file_fps == pytest.approx(25.0, abs=0.5)
    finally:
        src.stop()


def test_real_time_pacing(tmp_path: Path):
    p = tmp_path / "pace.mp4"
    _write_mp4(p, n_frames=60, fps=25)
    src = FileFrameSource(video_path=p)
    t0 = time.monotonic()
    src.start()
    try:
        target_count = 30
        deadline = t0 + 5.0
        while (src.get_frame_count() < target_count
               and time.monotonic() < deadline):
            time.sleep(0.01)
        elapsed = time.monotonic() - t0
        assert src.get_frame_count() >= target_count
        # 30 frames @ 25fps = 1.2s real-time pace; allow generous
        # slack for thread startup + scheduling jitter.
        assert 1.0 <= elapsed <= 1.8, (
            f"expected ~1.2s for 30 frames @25fps, got {elapsed:.3f}s")
    finally:
        src.stop()


def test_eof_behavior(short_mp4: Path, caplog: pytest.LogCaptureFixture):
    src = FileFrameSource(video_path=short_mp4)
    with caplog.at_level(logging.INFO, logger="frame_source"):
        src.start()
        # 10 frames @ 25fps drains in ~0.4s; give it a full second.
        time.sleep(1.2)
        # After EOF the capture loop has stopped — the last buffered
        # frame may linger but no more frames are being read.
        count_after_eof = src.get_frame_count()
        time.sleep(0.3)
        assert src.get_frame_count() == count_after_eof
        src.stop()
    assert any("[FILE-FRAME-SOURCE-EOF]" in r.getMessage()
               for r in caplog.records), (
        "expected [FILE-FRAME-SOURCE-EOF] log entry")


def test_loop_mode(short_mp4: Path):
    src = FileFrameSource(video_path=short_mp4, loop=True)
    src.start()
    try:
        # Drain past one full pass (10 frames @ 25fps ~ 0.4s).
        time.sleep(0.8)
        first_pass_count = src.get_frame_count()
        assert first_pass_count > 10, (
            f"expected loop to advance past file length, "
            f"got {first_pass_count} frames")
        # After a loop, get_latest still returns a valid frame.
        assert src.get_latest_bgr() is not None
    finally:
        src.stop()


def test_start_offset(long_mp4: Path):
    offset = 10.0
    src = FileFrameSource(video_path=long_mp4, start_offset_s=offset)
    src.start()
    try:
        frame = _wait_for_frame(src)
        assert frame is not None
        # cv2 reports the next-read position in ms — after the seek
        # it should sit at or just past 10_000 ms.
        pos_ms = src._cap.get(cv2.CAP_PROP_POS_MSEC)
        assert pos_ms >= offset * 1000.0, (
            f"expected seek position >= {offset*1000}ms, got {pos_ms}ms")
    finally:
        src.stop()


def test_make_frame_source_factory_with_file(
        short_mp4: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRAME_SOURCE", "file")
    monkeypatch.setenv("FRAME_SOURCE_FILE", str(short_mp4))
    monkeypatch.delenv("FRAME_SOURCE_FILE_LOOP", raising=False)
    monkeypatch.delenv("FRAME_SOURCE_FILE_OFFSET_S", raising=False)
    src = make_frame_source()
    assert isinstance(src, FileFrameSource)
    assert src.video_path == str(short_mp4)


def test_make_frame_source_file_requires_path(
        monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRAME_SOURCE", "file")
    monkeypatch.delenv("FRAME_SOURCE_FILE", raising=False)
    with pytest.raises(ValueError, match="FRAME_SOURCE_FILE"):
        make_frame_source()


def test_frames_use_replay_wall_clock(tmp_path: Path):
    """``get_latest_with_ts`` reports current replay wall-clock, not
    the recording's original timestamps or cv2.CAP_PROP_POS_MSEC.

    Sample three frames ~1s apart and check each ``ts`` is within
    100ms of ``time.time()`` at the moment of read.  This is what
    ContinuousChunker + ball_analyzer._frame_buffer_raw rely on to
    share a timestamp domain.
    """
    p = tmp_path / "wallclock.mp4"
    _write_mp4(p, n_frames=25 * 4, fps=25)
    src = FileFrameSource(video_path=p)
    src.start()
    try:
        deadline = time.monotonic() + 2.0
        while src.get_latest_with_ts() is None:
            if time.monotonic() > deadline:
                pytest.fail("FileFrameSource produced no frame within 2s")
            time.sleep(0.01)

        for _ in range(3):
            t_read = time.time()
            entry = src.get_latest_with_ts()
            assert entry is not None
            ts, frame = entry
            assert frame is not None
            assert abs(ts - t_read) < 0.1, (
                f"frame ts {ts} differs from wall-clock {t_read} by "
                f"{ts - t_read:.3f}s — domain leaked from recording")
            now = time.time()
            recording_clock_ceiling = 24 * 3600.0
            assert ts > now - recording_clock_ceiling, (
                f"ts {ts} looks like a recording-relative offset, "
                f"not live wall-clock {now}")
            time.sleep(1.0)
    finally:
        src.stop()
