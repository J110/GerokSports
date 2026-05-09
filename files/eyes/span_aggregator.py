"""SpanAggregator + score-event matcher (§4-§5 of design memo).

Aggregates ``(timestamp, frame_class)`` observations from
``OpenScout`` into closed contiguous-class spans with hysteresis.
Committed spans may have any ``frame_class`` (``action``, ``replay``,
etc.); ``set_committed_callback`` runs for every committed class, not
only action—downstream writers decide how to persist each.

  * A new observation extends the open span if its class matches.
  * One dissenting observation under ``SAME_CLASS_GAP_TOL`` is
    absorbed (handles single-frame Scout flickers, see §11.7 of the
    Scout per-frame validation memo).
  * Two dissenting obs OR a wall-clock gap ≥ ``SOFT_GAP_TOLERANCE_S``
    force-closes the open span and starts a new one.
  * Spans shorter than ``MIN_SPAN_FRAMES`` are dropped on commit
    (filters single-frame singletons that drove FP_other in §11.4).
  * Closed spans are pruned by ``end_ts < now − SPAN_RETENTION_S``;
    the retention mirrors ``BallAnalyzer.TAGGED_BUFFER_RETENTION_S=90.0``.

The matcher (`SpanAggregator.match_span_to_event`) implements §5.1's
tagged-tuple selector:

  * ``("no_match", None)`` — no qualifying action span.
  * ``("open_scout_span", (start_ts, end_ts))`` — single survivor;
    commit it.
  * ``("defer_to_legacy", None)`` — multiple survivors; v1 punts to
    the existing ``DeliveryWindowRecorder._find_span`` per §5.2.

Thread model: ``add_classification`` and ``match_span_to_event`` may
be called from different threads (capture/main + dwr-worker), so all
state is guarded by ``self._lock``.  Lock hold times are O(spans),
which is bounded at ≲200 entries per the 90 s retention window.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# Mirror the existing DWR constants — single source of truth for the
# event-window math so changes there propagate here.
from delivery_window_recorder import (
    LOOKBACK_S,
    MAX_END_TO_EVENT_GAP_S,
    POST_EVENT_EXCLUSION_S,
)

log = logging.getLogger("span_aggregator")
try:
    from eyes.cricket_logger import _ensure_file_handler
    log.addHandler(_ensure_file_handler())
    log.setLevel(logging.INFO)
except Exception:
    pass

# ── Tunables (§4.1 of design memo) ─────────────────────────────────
MIN_SPAN_FRAMES: int = 2
SAME_CLASS_GAP_TOL: int = 1
SOFT_GAP_TOLERANCE_S: float = 7.0
SPAN_RETENTION_S: float = 90.0
# Filter spans whose duration is too short to be a real delivery
# (action spans of 0 s come from a single-obs span where start_ts ==
# end_ts).  At 1 fps OpenScout, MIN_SPAN_FRAMES=2 already implies the
# end-start gap is ≥ ~1 s in practice; the explicit duration filter
# below is the §5.1 ``MIN_ACTION_SPAN_S=2.0`` rule.
MIN_ACTION_SPAN_S: float = 2.0

# Keep the history of class-text samples bounded — three previews per
# span is plenty for QA / shadow telemetry without bloating the
# delivery_dir json.
_TEXT_SAMPLES_PER_SPAN = 3
_TEXT_SAMPLE_MAX_CHARS = 240


@dataclass
class Span:
    """Closed contiguous-class span emitted by ``SpanAggregator``."""

    start_ts: float
    end_ts: float
    frame_class: str
    frame_count: int
    text_samples: list[str] = field(default_factory=list)
    # Auto-incremented per ``SpanAggregator`` instance.  Lets the
    # OpenScout span archive name per-span dirs deterministically and
    # lets ``DeliveryWindowRecorder`` correlate matched_to_event back
    # to the same on-disk bundle.  0 means "unassigned" (legacy
    # construction path that bypasses ``_commit_locked``).
    span_id: int = 0

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_ts - self.start_ts)

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "start_ts": round(self.start_ts, 3),
            "end_ts": round(self.end_ts, 3),
            "frame_class": self.frame_class,
            "frame_count": self.frame_count,
            "duration_s": round(self.duration_s, 3),
        }


class SpanAggregator:
    """State machine over per-frame OpenScout classifications."""

    def __init__(self,
                 *,
                 min_span_frames: int = MIN_SPAN_FRAMES,
                 same_class_gap_tol: int = SAME_CLASS_GAP_TOL,
                 soft_gap_tolerance_s: float = SOFT_GAP_TOLERANCE_S,
                 retention_s: float = SPAN_RETENTION_S):
        self._min_span_frames = min_span_frames
        self._same_class_gap_tol = same_class_gap_tol
        self._soft_gap_tolerance_s = soft_gap_tolerance_s
        self._retention_s = retention_s

        self._lock = threading.Lock()

        self._current_cls: str | None = None
        self._span_start_ts: float = 0.0
        self._span_last_ts: float = 0.0
        self._span_n: int = 0
        self._gap_obs: int = 0
        self._text_samples: list[str] = []

        self._closed: collections.deque[Span] = collections.deque()
        self.observations_recorded = 0
        self.spans_committed = 0
        self.singletons_dropped = 0
        # Span-id allocator (1-indexed so ``span_id == 0`` reads as
        # "unassigned" in downstream code).
        self._next_span_id: int = 1
        # Optional callback invoked on every committed span, OUTSIDE
        # the aggregator lock.  Wired by ``BallAnalyzer`` to the
        # OpenScout span archive (see ``openscout_persistence.py``).
        self._on_committed_cb: Callable[[Span], None] | None = None

    # ── Public API ─────────────────────────────────────────────

    def add_classification(self,
                           ts: float,
                           frame_class: str,
                           text: str | None = None) -> None:
        """Feed one ``(ts, class)`` observation.  Thread-safe."""
        if not isinstance(frame_class, str) or not frame_class:
            return
        committed: list[Span] = []
        with self._lock:
            self._add_locked(ts, frame_class, text,
                             committed_out=committed)
            self._prune_locked(ts)
        for sp in committed:
            self._fire_committed(sp)

    def set_committed_callback(
            self,
            cb: "Callable[[Span], None] | None") -> None:
        """Register a single callback fired (outside the lock) for
        every span this aggregator commits.  Pass ``None`` to detach.
        Replaces any prior callback.
        """
        self._on_committed_cb = cb

    def get_spans_in_range(self,
                           start_ts: float,
                           end_ts: float,
                           frame_class: str | None = None,
                           ) -> list[Span]:
        """Return committed spans overlapping ``[start_ts, end_ts]``.

        Optionally filter to a single ``frame_class``.  The currently
        open span is NOT returned — only committed spans are visible
        to the matcher.  This keeps span boundaries stable while
        async OpenScout calls are still landing.
        """
        with self._lock:
            return [
                s for s in self._closed
                if s.start_ts <= end_ts and s.end_ts >= start_ts
                and (frame_class is None or s.frame_class == frame_class)
            ]

    def prune_older_than(self, cutoff_ts: float) -> int:
        """Drop spans whose ``end_ts < cutoff_ts``.  Returns count."""
        with self._lock:
            n0 = len(self._closed)
            while self._closed and self._closed[0].end_ts < cutoff_ts:
                self._closed.popleft()
            return n0 - len(self._closed)

    def snapshot(self) -> list[Span]:
        """Read-only copy of all committed spans (newest last)."""
        with self._lock:
            return list(self._closed)

    def stats(self) -> dict:
        with self._lock:
            return {
                "observations": self.observations_recorded,
                "spans_committed": self.spans_committed,
                "singletons_dropped": self.singletons_dropped,
                "open_class": self._current_cls,
                "open_n": self._span_n,
                "closed_count": len(self._closed),
            }

    def force_close(self, now: float | None = None) -> None:
        """Commit the open span (if any).  Used by external timers
        (``BallAnalyzer.recorder_tick``) when the broadcast goes
        quiet so we don't keep an action span open across an ad
        break that paused OpenScout."""
        committed: list[Span] = []
        with self._lock:
            sp = self._commit_locked()
            if sp is not None:
                committed.append(sp)
            self._current_cls = None
            self._gap_obs = 0
            if now is not None:
                self._prune_locked(now)
        for sp in committed:
            self._fire_committed(sp)

    # ── Score-event matcher (§5.1) ─────────────────────────────

    def match_span_to_event(self,
                            event_ts: float,
                            *,
                            lookback_s: float = LOOKBACK_S,
                            post_event_exclusion_s: float = POST_EVENT_EXCLUSION_S,
                            max_end_to_event_gap_s: float = MAX_END_TO_EVENT_GAP_S,
                            min_action_span_s: float = MIN_ACTION_SPAN_S,
                            ) -> tuple[str, Optional[tuple[float, float]]]:
        """Return one of:
          ("no_match", None)
          ("open_scout_span", (start_ts, end_ts))
          ("defer_to_legacy", None)

        See §5.1 of the design memo.  Backward-compatible 2-tuple
        return; callers that need the matched ``span_id`` (for the
        OpenScout archive's ``note_match_to_event`` callback) should
        use :meth:`match_span_to_event_detailed` instead.
        """
        verdict, bounds, _sid = self.match_span_to_event_detailed(
            event_ts,
            lookback_s=lookback_s,
            post_event_exclusion_s=post_event_exclusion_s,
            max_end_to_event_gap_s=max_end_to_event_gap_s,
            min_action_span_s=min_action_span_s,
        )
        return (verdict, bounds)

    def match_span_to_event_detailed(
            self,
            event_ts: float,
            *,
            lookback_s: float = LOOKBACK_S,
            post_event_exclusion_s: float = POST_EVENT_EXCLUSION_S,
            max_end_to_event_gap_s: float = MAX_END_TO_EVENT_GAP_S,
            min_action_span_s: float = MIN_ACTION_SPAN_S,
            ) -> tuple[str,
                       Optional[tuple[float, float]],
                       Optional[int]]:
        """Same selection logic as :meth:`match_span_to_event` but
        also returns the matched ``span_id`` (or ``None`` for
        ``no_match`` / ``defer_to_legacy``).
        """
        lo = event_ts - lookback_s
        hi = event_ts - post_event_exclusion_s
        if hi <= lo:
            return ("no_match", None, None)

        candidates = self.get_spans_in_range(lo, hi, frame_class="action")
        candidates = [
            s for s in candidates if s.duration_s >= min_action_span_s
        ]
        candidates = [
            s for s in candidates
            if (event_ts - s.end_ts) <= max_end_to_event_gap_s
        ]

        n = len(candidates)
        if n == 0:
            log.info(
                f"[OPEN-SCOUT-SELECT] no_candidates "
                f"event_ts={event_ts:.2f} lo={lo:.2f} hi={hi:.2f} "
                f"→ no_match")
            return ("no_match", None, None)

        if n == 1:
            s = candidates[0]
            log.info(
                f"[OPEN-SCOUT-SELECT] single_candidate "
                f"start={s.start_ts:.2f} end={s.end_ts:.2f} "
                f"n={s.frame_count} span_id={s.span_id} "
                f"→ open_scout_span")
            return ("open_scout_span",
                    (s.start_ts, s.end_ts),
                    s.span_id or None)

        candidates.sort(key=lambda s: s.start_ts)
        bounds = [
            (round(s.start_ts, 2), round(s.end_ts, 2),
             s.frame_count, s.span_id)
            for s in candidates
        ]
        log.info(
            f"[OPEN-SCOUT-SELECT] multi_candidate n={n} "
            f"event_ts={event_ts:.2f} candidates={bounds} "
            f"→ defer_to_legacy")
        return ("defer_to_legacy", None, None)

    # ── Internals ──────────────────────────────────────────────

    def _fire_committed(self, sp: Span) -> None:
        cb = self._on_committed_cb
        if cb is None:
            return
        try:
            cb(sp)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[SPAN-AGG] on_committed cb error: {e}")

    def _add_locked(self,
                    ts: float,
                    cls: str,
                    text: str | None,
                    *,
                    committed_out: list[Span] | None = None) -> None:
        self.observations_recorded += 1

        # Soft gap: too long since last obs → force-close anything open.
        if (self._current_cls is not None
                and (ts - self._span_last_ts)
                > self._soft_gap_tolerance_s):
            sp = self._commit_locked()
            if sp is not None and committed_out is not None:
                committed_out.append(sp)
            self._current_cls = None
            self._gap_obs = 0

        # Matching obs extends the open span.
        if cls == self._current_cls:
            self._span_last_ts = ts
            self._span_n += 1
            self._gap_obs = 0
            self._maybe_record_text(text)
            return

        # Dissenting obs under tolerance — count toward gap, hold open.
        if (self._current_cls is not None
                and self._gap_obs < self._same_class_gap_tol):
            self._gap_obs += 1
            return

        # Transition — close current (if any), open new.
        if self._current_cls is not None:
            sp = self._commit_locked()
            if sp is not None and committed_out is not None:
                committed_out.append(sp)

        self._current_cls = cls
        self._span_start_ts = ts
        self._span_last_ts = ts
        self._span_n = 1
        self._gap_obs = 0
        self._text_samples = []
        self._maybe_record_text(text)

    def _maybe_record_text(self, text: str | None) -> None:
        if text and len(self._text_samples) < _TEXT_SAMPLES_PER_SPAN:
            self._text_samples.append(text[:_TEXT_SAMPLE_MAX_CHARS])

    def _commit_locked(self) -> Span | None:
        if self._current_cls is None:
            return None
        if self._span_n < self._min_span_frames:
            self.singletons_dropped += 1
            return None
        span_id = self._next_span_id
        self._next_span_id += 1
        span = Span(
            start_ts=self._span_start_ts,
            end_ts=self._span_last_ts,
            frame_class=self._current_cls,
            frame_count=self._span_n,
            text_samples=list(self._text_samples),
            span_id=span_id,
        )
        self._closed.append(span)
        self.spans_committed += 1
        return span

    def _prune_locked(self, now: float) -> None:
        cutoff = now - self._retention_s
        while self._closed and self._closed[0].end_ts < cutoff:
            self._closed.popleft()


__all__ = [
    "Span",
    "SpanAggregator",
    "MIN_SPAN_FRAMES",
    "SAME_CLASS_GAP_TOL",
    "SOFT_GAP_TOLERANCE_S",
    "SPAN_RETENTION_S",
    "MIN_ACTION_SPAN_S",
]
