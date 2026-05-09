"""V3SpanAggregator — production wiring for ChunkerV3.

Mirrors the public surface of :class:`SpanAggregator` (``add_*``,
``find_span``, ``snapshot``, retention pruning) so :class:`Delivery
WindowRecorder` can consult v3 alongside the legacy SpanAggregator
without bespoke plumbing.

Per-frame inputs land via :meth:`add_frame` (full payload) — the
hookpoint is the same OpenScout result-sink that already pushes into
``ball_analyzer.record_open_classification``.  See
``files/test_pipeline.py`` openscout_loop wiring.

Graceful degrade: if any frame field is missing the v3 algorithm
silently returns ``None`` from ``find_span``; the caller falls back
to the legacy span.

Thread-safe (``threading.Lock``).  Consumed from the asyncio main
loop AND occasionally from the DWR worker thread, so the lock matters.
"""
from __future__ import annotations

import collections
import threading
from typing import Optional

from eyes.chunker_v3 import (
    FrameInput,
    find_consequential_window,
)


# Retention mirrors SpanAggregator.SPAN_RETENTION_S — keep enough
# history that a score event arriving 90 s after the cluster can still
# be classified.
DEFAULT_RETENTION_S: float = 90.0
# Cap stored frames to a hard ceiling so a stuck consumer doesn't grow
# memory unbounded.  At 1.0 s OpenScout cadence + 90 s retention, the
# expected steady-state count is ~90; 1024 is comfortably padded for
# bursty cadence.
_MAX_FRAMES = 1024


class V3SpanAggregator:
    """Per-match rolling buffer of FrameInputs + chunker_v3 entrypoint."""

    def __init__(self, *, retention_s: float = DEFAULT_RETENTION_S):
        self._retention_s = float(retention_s)
        self._lock = threading.Lock()
        self._frames: collections.deque[FrameInput] = collections.deque(
            maxlen=_MAX_FRAMES)
        self._adds_total = 0
        self._adds_dropped_invalid = 0
        self._lookups_total = 0
        self._lookups_returned = 0

    # ── Public API ─────────────────────────────────────────────

    def add_frame(self,
                  ts: float,
                  *,
                  prod_cam: str | None,
                  prod_phase: str | None,
                  v2_broadcast_tag: str | None,
                  v2_class: str | None,
                  open_desc: str | None) -> None:
        """Record one per-frame Scout payload.  Thread-safe.

        All fields except ``ts`` are coerced to empty string when None.
        Missing fields don't raise; the v3 algorithm just gets less
        signal.
        """
        if ts is None:
            return
        try:
            ts_f = float(ts)
        except (TypeError, ValueError):
            return
        if not (open_desc or v2_class or prod_cam):
            self._adds_dropped_invalid += 1
            return
        f = FrameInput(
            ts=ts_f,
            prod_cam=str(prod_cam or ""),
            prod_phase=str(prod_phase or ""),
            v2_broadcast_tag=str(v2_broadcast_tag or ""),
            v2_class=str(v2_class or ""),
            open_desc=str(open_desc or ""),
        )
        with self._lock:
            self._frames.append(f)
            self._adds_total += 1
            self._prune_locked(ts_f)

    def find_span(self,
                  event_ts: float,
                  *,
                  lookback_s: float | None = None,
                  ) -> Optional[tuple[float, float]]:
        """Return ``(start_ts, end_ts)`` for the consequential delivery
        window leading up to ``event_ts``, or ``None`` if no confirmed
        cluster exists.

        ``lookback_s`` constrains the candidate frames to
        ``[event_ts - lookback_s, event_ts + small_post]``; defaults to
        the retention window.  The chunker itself bounds the window to
        4 s on each side of the cluster.
        """
        with self._lock:
            self._lookups_total += 1
            window_lo = event_ts - (
                lookback_s if lookback_s is not None else self._retention_s)
            # A small post-event horizon catches umpire / DRS chunks
            # that follow the score event by a few seconds.
            window_hi = event_ts + 8.0
            frames = [
                f for f in self._frames
                if window_lo <= f.ts <= window_hi
            ]
        if not frames:
            return None
        try:
            window = find_consequential_window(frames, event_ts=event_ts)
        except Exception:  # noqa: BLE001
            return None
        if window is not None:
            with self._lock:
                self._lookups_returned += 1
        return window

    def snapshot_frames(self) -> list[FrameInput]:
        with self._lock:
            return list(self._frames)

    def prune_older_than(self, cutoff_ts: float) -> int:
        with self._lock:
            n0 = len(self._frames)
            kept = [f for f in self._frames if f.ts >= cutoff_ts]
            self._frames.clear()
            self._frames.extend(kept)
            return n0 - len(self._frames)

    def stats(self) -> dict:
        with self._lock:
            return {
                "adds_total": self._adds_total,
                "adds_dropped_invalid": self._adds_dropped_invalid,
                "lookups_total": self._lookups_total,
                "lookups_returned_window": self._lookups_returned,
                "frames_buffered": len(self._frames),
            }

    # ── Internals ──────────────────────────────────────────────

    def _prune_locked(self, now: float) -> None:
        cutoff = now - self._retention_s
        while self._frames and self._frames[0].ts < cutoff:
            self._frames.popleft()


__all__ = ["V3SpanAggregator", "DEFAULT_RETENTION_S"]
