"""Tests for OpenScoutShadowRunner independent ingest thread (§12)."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from openscout_shadow.shadow_runner import OpenScoutShadowRunner


class _StubFrameSource:
    def __init__(self, frame: np.ndarray, fresh_each_call: bool = True):
        self._frame = frame
        self._fresh_each_call = fresh_each_call

    def get_latest_bgr(self):
        if self._fresh_each_call:
            return self._frame.copy()
        return self._frame


def _make_runner(tmp_path: Path, **kwargs) -> OpenScoutShadowRunner:
    return OpenScoutShadowRunner(
        session_id="test",
        output_dir=tmp_path,
        **kwargs,
    )


def test_shadow_runner_ingests_at_configured_cadence(tmp_path):
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    src = _StubFrameSource(frame, fresh_each_call=True)
    runner = _make_runner(tmp_path, frame_source=src, ingest_fps=10.0)
    runner.start()
    try:
        time.sleep(1.0)
    finally:
        runner.stop()
    assert runner._ingest_thread is not None
    assert not runner._ingest_thread.is_alive()
    assert runner.stats()["frames_received"] >= 8


def test_shadow_runner_no_ingest_thread_when_no_source(tmp_path):
    runner = _make_runner(tmp_path, frame_source=None, ingest_fps=10.0)
    runner.start()
    try:
        assert runner._ingest_thread is None
        assert runner._has_own_ingest is False
        time.sleep(0.5)
        assert runner.stats()["frames_received"] == 0
    finally:
        runner.stop()


def test_shadow_runner_duplicate_frames_skipped(tmp_path):
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    src = _StubFrameSource(frame, fresh_each_call=False)
    runner = _make_runner(tmp_path, frame_source=src, ingest_fps=10.0)
    runner.start()
    try:
        time.sleep(1.0)
    finally:
        runner.stop()
    assert runner.stats()["frames_received"] == 1
