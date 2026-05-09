"""Streaming delivery-span selector — Stage 2 of the three-stage
Motion → Scout+Aggregator → Qwen pipeline.

Migrates the per-clip v4 sub-clip isolation logic
(``files/scripts/sub_clip_isolation_v4/extract_spans.py``,
validated 17/20 perfect at
``files/docs/investigations/sub_clip_delivery_isolation_v4.md``)
to a streaming flow over the live Scout per-frame output.

Key differences vs the v4 research wrapper:

  * v4 processed pre-cut clips, then *anchor-selected* one delivery
    per clip relative to ``event_offset_s``.  Streaming receives a
    continuous Scout result flow and emits *every* qualifying
    delivery as it closes — there is no per-clip anchor here, so
    the v3/v4 anchor-selection logic is dropped.
  * v4 fed every frame in a clip, then called ``force_close`` once
    at end-of-clip.  Streaming must decide, per closure, whether the
    span is *definitively* closed (no late-arriving action frames
    will extend it).

Streaming closure rule
----------------------

A span is "closed and ready to emit" when **all** hold:

  1. ``SpanAggregator`` has committed it (via dissent transition,
     ``SOFT_GAP_TOLERANCE_S`` soft-gap timeout, or replay/ad
     hard-close from this module's pre-pass).
  2. At least ``DEFAULT_CLOSURE_HOLD_S`` (3.0 s) of new frame
     timestamps have arrived since the commit.  This guard exists
     because the aggregator's dissent absorption (one tolerated
     dissenting obs under ``SAME_CLASS_GAP_TOL=1``) means a span
     that *appeared* to end at ts=T can still be re-extended if
     another action obs arrives at ts=T+Δ before transition fires.
     The 3 s window comfortably exceeds the 2.5 s soft-gap
     tolerance, so any plausible extension would already have
     committed (or not) by then.
  3. The committed span passes the v4 post-filters:
     ``frame_count >= min_run_frames`` (default 5) and
     ``duration_s >= min_span_duration_s`` (default 2.0 s).

Hard-close pre-pass
-------------------

When the incoming Scout class is ``replay`` or ``ad`` we do **not**
hand it to ``SpanAggregator``.  Instead we call
``SpanAggregator.force_close(now=ts)`` to commit any open action
span on the spot, then move on.  This mirrors v4's pre-pass and
prevents replay highlights or ad bumpers from getting glued onto
the trailing end of a real delivery via dissent absorption.  A
counter is attached to the just-committed span as
``hard_close_count`` for QA / shadow telemetry.

Padding
-------

On emit, raw bounds get ``padding_s`` (default 1.0 s) symmetric
padding.  ``padded_start`` is clamped at 0; ``padded_end`` is
clamped to the latest observed frame timestamp.  In normal
streaming the closure hold (3 s) guarantees we have ≥ 3 s of
post-span frames, so a 1 s padding is never end-clamped.  On
``flush()`` (shutdown / Stage-1 window close) we may emit pending
spans without that buffer, in which case the clamp does fire.

Memory bounds
-------------

A ring buffer of recent Scout results is kept for ``action_ratio``
computation at emit time, bounded by **both**:

  * ``max_buffered_frames`` (default 120) — hard cap via
    ``collections.deque(maxlen=...)``.
  * ``rolling_window_s`` (default 30 s) — pruned on each ingest.

Pending-emit storage is naturally bounded by closure hold (3 s)
plus production Scout cadence (≤ 1 fps), so at most a handful of
spans ever sit in ``self._pending`` at once.

Configuration history
---------------------

Defaults trace from the v4 validation memo:

  * ``min_run_frames=5``      v4 ``MIN_RUN_FRAMES``
  * ``min_span_duration_s=2`` v4/v3 ``MIN_ACTION_SPAN_S``
  * ``padding_s=1.0``          v4 ``SUB_CLIP_PADDING_S`` env default
  * ``soft_gap_tolerance_s=2.5``  ``SpanAggregator`` default
  * ``rolling_window_s=30``    enough for a single Scout-emerging
    delivery (~10-25 s) plus closure hold; tightened from the
    aggregator's 90 s retention since this module only needs the
    most recent in-flight span.
"""

from __future__ import annotations

import collections
import logging
from dataclasses import dataclass, field
from typing import Callable

from eyes.span_aggregator import Span, SpanAggregator

log = logging.getLogger("delivery_span_selector")

HARD_CLOSE_CLASSES: frozenset[str] = frozenset({"replay", "ad"})

# Closure hold: see module docstring §"Streaming closure rule".
DEFAULT_CLOSURE_HOLD_S: float = 3.0

# Temporal anchoring window (sub_clip_delivery_isolation_v4.md §8).
# A committed span is considered to "belong to" a score event iff its
# end_ts lands within ``[event_ts - ANCHOR_PRE_S, event_ts + ANCHOR_POST_S]``.
ANCHOR_PRE_S: float = 12.0
ANCHOR_POST_S: float = 2.0
SCORE_EVENT_BUFFER_MAX: int = 32
SCORE_EVENT_BUFFER_TRIM: int = 16


@dataclass
class DeliverySpan:
    """A delivery span emitted by ``DeliverySpanSelector``.

    ``start_ts``/``end_ts`` are post-padding (the bounds Stage 3
    Qwen should consume).  ``raw_*`` are the pre-padding aggregator
    bounds, retained for diagnostic correlation with the underlying
    ``SpanAggregator`` ``Span``.
    """

    start_ts: float
    end_ts: float
    raw_start_ts: float
    raw_end_ts: float
    frame_count: int
    action_ratio: float
    max_consecutive_action: int
    selection_basis: str
    hard_close_count: int
    diagnostic: dict = field(default_factory=dict)


class DeliverySpanSelector:
    """Streaming delivery span selector.  Consumes Scout per-frame
    results in real time, emits closed delivery spans through
    ``on_span_emitted`` once they are definitively bounded.

    See module docstring for the closure rule and configuration
    history.  Not thread-safe — wrap with external synchronization
    if Scout results arrive from multiple threads.
    """

    def __init__(
        self,
        on_span_emitted: Callable[[DeliverySpan], None],
        *,
        min_run_frames: int = 5,
        min_span_duration_s: float = 2.0,
        padding_s: float = 1.0,
        soft_gap_tolerance_s: float = 2.5,
        rolling_window_s: float = 30.0,
        max_buffered_frames: int = 120,
        closure_hold_s: float = DEFAULT_CLOSURE_HOLD_S,
    ):
        self._on_span_emitted = on_span_emitted
        self._min_run_frames = min_run_frames
        self._min_span_duration_s = min_span_duration_s
        self._padding_s = padding_s
        self._rolling_window_s = rolling_window_s
        self._max_buffered_frames = max_buffered_frames
        self._closure_hold_s = closure_hold_s

        self._aggregator = SpanAggregator(
            soft_gap_tolerance_s=soft_gap_tolerance_s,
        )
        self._aggregator.set_committed_callback(self._on_aggregator_commit)

        self._frame_buffer: collections.deque[dict] = collections.deque(
            maxlen=max_buffered_frames,
        )

        # Spans waiting for the post-commit hold to elapse.  Keyed by
        # span_id so re-entrancy on the same span is a no-op.  Value
        # is (Span, hard_close_count_attributed, close_observed_ts).
        self._pending: dict[int, tuple[Span, int, float]] = {}

        # Hard-close attribution.  Each ``replay``/``ad`` obs
        # increments this; ``_on_aggregator_commit`` reads and
        # resets it.  Reset is unconditional so a singleton-dropped
        # commit (no callback fired) does not leak its count to the
        # next emit — see the explicit reset in ``add_scout_result``.
        self._hard_close_count_for_open_span: int = 0

        self._last_observed_ts: float | None = None

        # Score-event timestamps surfaced by the pipeline via
        # ``mark_score_event``.  Used to temporally anchor span emission
        # per sub_clip_delivery_isolation_v4.md §8.7.  Bounded buffer.
        self._score_events: list[float] = []

    # ── Public API ─────────────────────────────────────────────

    def mark_score_event(self, ts: float) -> None:
        """Record a score-event timestamp.

        Used to anchor span selection: prefer spans ending in
        ``[ts - ANCHOR_PRE_S, ts + ANCHOR_POST_S]``; reject spans
        starting after ``ts``.  See sub_clip_delivery_isolation_v4.md
        §8.7.
        """
        self._score_events.append(float(ts))
        if len(self._score_events) > SCORE_EVENT_BUFFER_MAX:
            self._score_events = self._score_events[-SCORE_EVENT_BUFFER_TRIM:]

    def add_scout_result(self, scout_result: dict) -> None:
        """Ingest one per-frame Scout classification.

        Expected fields: ``ts`` (float seconds), ``frame_class``
        (one of action / replay / ad / umpire / other / falsy), and
        optional ``raw_description``.  Falsy / missing
        ``frame_class`` (e.g., a Scout timeout) is buffered for
        ``_last_observed_ts`` tracking but not fed to the aggregator,
        matching v4's ``if not cls: continue`` behavior.
        """
        ts = float(scout_result["ts"])
        cls = scout_result.get("frame_class")
        text = scout_result.get("raw_description")

        self._last_observed_ts = ts
        self._frame_buffer.append({"ts": ts, "frame_class": cls})
        self._prune_buffer(ts)

        if not cls:
            self._maybe_emit_ready(ts)
            return

        if cls in HARD_CLOSE_CLASSES:
            self._hard_close_count_for_open_span += 1
            self._aggregator.force_close(now=ts)
            # Belt-and-suspenders: if no callback fired (the open
            # span was dropped as a singleton), reset so the count
            # does not leak forward to a later commit.
            self._hard_close_count_for_open_span = 0
            self._maybe_emit_ready(ts)
            return

        self._aggregator.add_classification(ts, cls, text=text)
        self._maybe_emit_ready(ts)

    def flush(self) -> None:
        """Force-close the aggregator and drain pending spans.

        Call on shutdown or when an upstream Stage-1 candidate
        window closes.  Pending spans are emitted in chronological
        order regardless of the closure hold.  Temporal-anchoring
        rules still apply on flush.
        """
        self._aggregator.force_close()
        ready = sorted(
            self._pending.items(),
            key=lambda kv: kv[1][0].end_ts,
        )
        for span_id, (span, hc, _close_ts) in ready:
            basis = self._anchor_decision(span)
            if basis is None:
                continue
            self._emit(span, hc, selection_basis=basis)
        self._pending.clear()

    # ── Internals ──────────────────────────────────────────────

    def _on_aggregator_commit(self, span: Span) -> None:
        # Reset hard-close attribution unconditionally — even
        # non-action and filtered commits end the open-span window.
        hc = self._hard_close_count_for_open_span
        self._hard_close_count_for_open_span = 0

        if span.frame_class != "action":
            return
        if span.frame_count < self._min_run_frames:
            return
        if span.duration_s < self._min_span_duration_s:
            return

        # The aggregator does not surface the ts that triggered the
        # commit, so anchor closure-hold to the latest observed ts.
        # ``_last_observed_ts`` is updated at the head of
        # ``add_scout_result`` (and during ``force_close`` it equals
        # whatever ts was passed in).
        close_ts = (self._last_observed_ts
                    if self._last_observed_ts is not None
                    else span.end_ts)
        self._pending[span.span_id] = (span, hc, close_ts)

    def _maybe_emit_ready(self, now: float) -> None:
        ready: list[tuple[int, Span, int]] = []
        for sid, (sp, hc, close_ts) in self._pending.items():
            if (now - close_ts) >= self._closure_hold_s:
                ready.append((sid, sp, hc))
        ready.sort(key=lambda t: t[1].end_ts)
        for sid, sp, hc in ready:
            del self._pending[sid]
            basis = self._anchor_decision(sp)
            if basis is None:
                log.info(
                    "[span-selector] dropping post-event span "
                    f"sid={sp.span_id} "
                    f"raw=[{sp.start_ts:.2f},{sp.end_ts:.2f}] — "
                    "starts after all known score events")
                continue
            self._emit(sp, hc, selection_basis=basis)

    def _anchor_decision(self, span: Span) -> str | None:
        """Decide if a committed span should emit and tag its basis.

        See sub_clip_delivery_isolation_v4.md §8.7.

        Returns the ``selection_basis`` string for the emit, or
        ``None`` if the span should be dropped (post-event content with
        no matching score event).
        """
        if not self._score_events:
            return "fallback_no_event"
        candidates = [ts for ts in self._score_events
                      if ts >= span.start_ts]
        if not candidates:
            return None
        event_ts = max(candidates)
        lo = event_ts - ANCHOR_PRE_S
        hi = event_ts + ANCHOR_POST_S
        if lo <= span.end_ts <= hi:
            return "anchored_to_event_ts"
        return "fallback_longest_span"

    def _emit(self, span: Span, hard_close_count: int,
              selection_basis: str = "fallback_no_event") -> None:
        raw_start = span.start_ts
        raw_end = span.end_ts
        padded_start = max(0.0, raw_start - self._padding_s)

        last_obs = self._last_observed_ts
        if last_obs is None:
            padded_end = raw_end + self._padding_s
        else:
            padded_end = min(raw_end + self._padding_s, last_obs)

        action_ratio, max_consec = self._compute_window_stats(
            raw_start, raw_end, span.frame_count,
        )

        delivery = DeliverySpan(
            start_ts=padded_start,
            end_ts=padded_end,
            raw_start_ts=raw_start,
            raw_end_ts=raw_end,
            frame_count=span.frame_count,
            action_ratio=action_ratio,
            max_consecutive_action=max_consec,
            selection_basis=selection_basis,
            hard_close_count=hard_close_count,
            diagnostic={
                "span_id": span.span_id,
                "duration_s": round(span.duration_s, 3),
            },
        )
        try:
            self._on_span_emitted(delivery)
        except Exception as e:  # noqa: BLE001
            log.warning(f"on_span_emitted callback error: {e}")

    def _compute_window_stats(
        self,
        raw_start: float,
        raw_end: float,
        span_frame_count: int,
    ) -> tuple[float, int]:
        in_window = [
            f for f in self._frame_buffer
            if raw_start <= f["ts"] <= raw_end
        ]
        if not in_window:
            # Buffer may have been pruned past the span's left edge
            # (rare — only with rolling_window_s smaller than the
            # span itself).  Fall back to span_frame_count.
            return (1.0, span_frame_count)
        n_action = sum(1 for f in in_window
                       if f.get("frame_class") == "action")
        action_ratio = n_action / len(in_window)

        # Longest consecutive action run within the window.  Single
        # dissent absorption already happened upstream, but recompute
        # from the raw buffer for a faithful telemetry value.
        max_consec = 0
        cur = 0
        for f in in_window:
            if f.get("frame_class") == "action":
                cur += 1
                if cur > max_consec:
                    max_consec = cur
            else:
                cur = 0
        return (action_ratio, max_consec)

    def _prune_buffer(self, now: float) -> None:
        cutoff = now - self._rolling_window_s
        while self._frame_buffer and self._frame_buffer[0]["ts"] < cutoff:
            self._frame_buffer.popleft()


__all__ = [
    "DeliverySpan",
    "DeliverySpanSelector",
    "HARD_CLOSE_CLASSES",
    "DEFAULT_CLOSURE_HOLD_S",
    "ANCHOR_PRE_S",
    "ANCHOR_POST_S",
]
