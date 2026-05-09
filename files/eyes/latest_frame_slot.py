"""LatestFrameSlot — single-frame buffer with overwrite-on-write semantics.

Decouples a frame producer (capture loop) from a frame consumer (decoupled
OpenScout loop) so the two run at independent cadences without queueing.

The consumer always sees the newest available frame.  Intermediate frames
are intentionally dropped — for sampling-style consumers (OpenScout at
~1.0s cadence) skipping older frames is correct behaviour.

Two write modes:
  * Push:  call ``slot.set(frame, ts)`` from the producer side.
  * Pull:  pass ``source_fn=frames.get_latest`` at construction; the slot
           delegates ``get_latest()`` to that callable.  Useful when the
           upstream frame source already exposes latest-frame semantics
           (``CaptureCardFrameSource``) and a tee thread would just add
           contention.

Reads return ``(frame, ts, monotonic_set_time)`` so consumers can detect
stale frames by comparing ``monotonic_set_time`` against their own clock.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Tuple

import numpy as np

FrameTuple = Tuple[np.ndarray, float, float]


class LatestFrameSlot:
    """Single-slot frame buffer.  Thread-safe; overwrite-on-write."""

    def __init__(self,
                 source_fn: Optional[Callable[[], Optional[np.ndarray]]] = None):
        self._source_fn = source_fn
        self._frame: Optional[np.ndarray] = None
        self._ts: float = 0.0
        self._set_monotonic: float = 0.0
        self._lock = threading.Lock()
        self._writes = 0
        self._reads = 0

    def set(self, frame: np.ndarray, ts: float) -> None:
        with self._lock:
            self._frame = frame
            self._ts = float(ts)
            self._set_monotonic = time.monotonic()
            self._writes += 1

    async def get_latest(self) -> Optional[FrameTuple]:
        if self._source_fn is not None:
            try:
                f = self._source_fn()
            except Exception:  # noqa: BLE001
                return None
            if f is None:
                return None
            now = time.time()
            with self._lock:
                self._reads += 1
            return (f, now, time.monotonic())
        with self._lock:
            self._reads += 1
            if self._frame is None:
                return None
            return (self._frame, self._ts, self._set_monotonic)

    def stats(self) -> dict:
        with self._lock:
            return {
                "writes": self._writes,
                "reads": self._reads,
                "has_frame": self._frame is not None,
                "last_set_monotonic": self._set_monotonic,
            }


__all__ = ["LatestFrameSlot", "FrameTuple"]
