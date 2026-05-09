"""Integration hook for OpenScoutShadowRunner.

Wires the shadow runner into the main pipeline at the BallAnalyzer /
OpenScout dispatch boundary. Activation is gated by the SHADOW_MODE
env var; absent / != "1" returns None so callers no-op cheaply.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from openscout_shadow.shadow_runner import OpenScoutShadowRunner

log = logging.getLogger("openscout_shadow.hook")

SHADOW_MODE_ENV = "SHADOW_MODE"


def _make_frame_buffer_qwen(
    ball_analyzer,
    qwen_callable: Optional[Callable],
):
    """Build a Qwen wrapper that snapshots ball_analyzer._frame_buffer
    in the [start_ts, end_ts] window before invoking ``qwen_callable``.

    list() on a deque is atomic in CPython, so the snapshot is safe
    without explicit locking against the producer thread that appends
    to ``_frame_buffer`` (see ball_analyzer.py:2043).
    """
    def _qwen(*, span_start_ts, span_end_ts, span):
        buf = list(getattr(ball_analyzer, "_frame_buffer", ()) or ())
        frames = [
            (ts, fr) for (ts, fr) in buf
            if span_start_ts <= ts <= span_end_ts
        ]
        if qwen_callable is None:
            return {
                "qwen_disabled": True,
                "frame_count": len(frames),
            }
        return qwen_callable(frames=frames, span_meta={
            "start_ts": span.start_ts,
            "end_ts": span.end_ts,
            "raw_start_ts": span.raw_start_ts,
            "raw_end_ts": span.raw_end_ts,
            "action_ratio": span.action_ratio,
            "max_consecutive_action": span.max_consecutive_action,
            "hard_close_count": span.hard_close_count,
        })
    return _qwen


def attach_shadow_runner(
    ball_analyzer,
    session_id: str,
    qwen_classifier: Optional[Callable] = None,
    frame_source: Optional[Any] = None,
    ingest_fps: Optional[float] = None,
) -> Optional[OpenScoutShadowRunner]:
    """Construct + start the shadow runner if SHADOW_MODE=1.

    Returns the runner instance (caller pumps via add_frame /
    add_scout_result), or None when shadow mode is disabled.
    """
    if os.environ.get(SHADOW_MODE_ENV, "0") != "1":
        return None
    if frame_source is None:
        frame_source = getattr(ball_analyzer, "_capture_card", None)
    if ingest_fps is None:
        ingest_fps = float(os.environ.get("SHADOW_INGEST_FPS", "5.0"))
    qwen_wrapper = _make_frame_buffer_qwen(ball_analyzer, qwen_classifier)
    runner = OpenScoutShadowRunner(
        session_id=session_id,
        qwen_classifier=qwen_wrapper,
        log=log,
        frame_source=frame_source,
        ingest_fps=ingest_fps,
    )
    runner.start()
    log.info("[SHADOW] attached, session=%s", session_id)
    return runner


__all__ = ["attach_shadow_runner", "SHADOW_MODE_ENV"]
